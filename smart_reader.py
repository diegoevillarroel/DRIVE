"""
DRIVE — AI SSD Guardian
smart_reader.py — Reads SMART data from storage devices on Windows.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List

from models import DriveInfo

log = logging.getLogger("drive.smart")


class SmartReader:
    """
    Reads SMART health data from storage devices using smartmontools.
    Supports NVMe, SATA, and USB drives on Windows.
    """

    def __init__(self, smartctl_path: Optional[str] = None):
        self.smartctl_path = smartctl_path or self._find_smartctl()

    def _find_smartctl(self) -> Optional[str]:
        """Find smartctl in PATH or bundle."""
        # Check common locations
        candidates = [
            "smartctl.exe",  # system PATH
            "C:\\Program Files\\smartmontools\\bin\\smartctl.exe",
            "C:\\Program Files (x86)\\smartmontools\\bin\\smartctl.exe",
            str(Path(__file__).parent / "bin" / "smartctl.exe"),
            str(Path(__file__).parent.parent / "bin" / "smartctl.exe"),
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                log.info("Found smartctl at: %s", candidate)
                return candidate
        # Fall back to PATH
        for name in ["smartctl", "smartctl.exe"]:
            try:
                subprocess.run([name, "--version"], capture_output=True, timeout=5)
                log.info("smartctl found in PATH: %s", name)
                return name
            except (OSError, subprocess.TimeoutExpired):
                continue
        log.warning("smartctl not found — SSD health features will be limited")
        return None

    def _run_smartctl(self, args: List[str], timeout: int = 30) -> dict:
        """Run smartctl with JSON output and return parsed result."""
        if not self.smartctl_path:
            raise RuntimeError("smartctl not available")

        cmd = [self.smartctl_path] + args
        log.debug("Running: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"smartctl timed out after {timeout}s")
        except FileNotFoundError:
            raise RuntimeError(f"smartctl not found at: {self.smartctl_path}")

        if result.returncode not in (0, 0):
            # Some errors are non-fatal (e.g., device not supported)
            log.debug("smartctl returned %d: %s", result.returncode, result.stderr[:200])

        # Try JSON first
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            pass

        # Fall back to parsing text output
        return {"parse_error": True, "stdout": result.stdout, "stderr": result.stderr}

    def get_drives(self) -> List[dict]:
        """List all available storage devices."""
        try:
            output = self._run_smartctl(["--scan", "--json"])
            devices = output.get("devices", [])
            return devices if devices else []
        except Exception as e:
            log.error("Drive scan failed: %s", e)
            return []

    def get_drive_info(self, device: Optional[str] = None) -> DriveInfo:
        """
        Read SMART data for the primary drive.

        Strategy (in order):
        1. smartctl JSON (when installed) — best path
        2. WMI Win32_DiskDrive for model/serial/capacity (always works)
        3. Honest 'could not read SMART' — never returns fake 100% health
        """
        info = DriveInfo()

        # 1. Try smartctl first
        smart_data: dict = {}
        if self.smartctl_path:
            target = device
            try:
                if target is None:
                    drives = self.get_drives()
                    if drives:
                        target = drives[0].get("name") or drives[0].get("info", {}).get("name")
                if target:
                    smart_data = self._run_smartctl(["-j", "-a", target])
            except Exception as e:
                log.debug("smartctl call failed: %s", e)
                smart_data = {}

        # NVMe fields
        if "nvme_smart_health_information_log" in smart_data:
            nvme = smart_data["nvme_smart_health_information_log"]
            info.temperature_c = nvme.get("temperature")
            info.power_on_hours = nvme.get("power_on_hours")
            info.power_cycles = nvme.get("power_cycles")
            bw = nvme.get("data_units_written", 0)
            if isinstance(bw, list) and len(bw) >= 2:
                bw = bw[0]
            info.tbw_written_tb = round(bw * 512 / 1_000_000, 3)
            spare = nvme.get("available_spare")
            if spare is not None:
                info.spare_remaining_pct = int(spare)
                info.health_percent = int(spare)
            info.interface = "NVMe"
        # ATA/SATA fields
        if "ata_smart_attributes" in smart_data:
            ata = smart_data["ata_smart_attributes"]
            info.model = ata.get("model", info.model)
            info.serial = ata.get("serial", info.serial)
            info.firmware = ata.get("firmware", info.firmware)
            for attr in ata.get("table", []):
                id_num = attr.get("id")
                value = attr.get("value")
                thresh = attr.get("thresh")
                raw = (attr.get("raw", {}) or {}).get("string", "").strip()
                if id_num == 9:
                    info.power_on_hours = int(raw) if raw.isdigit() else value
                elif id_num == 177:
                    if value and thresh and thresh > 0:
                        info.health_percent = int((value / thresh) * 100)
                        info.wear_leveling = value
                elif id_num == 232 or id_num == 233:
                    info.health_percent = value
                elif id_num == 241:
                    if raw:
                        try:
                            parts = raw.split()
                            val = int(parts[0], 16) if parts else 0
                            info.tbw_written_tb = round(val * 512 / 1e12, 3)
                        except Exception:
                            pass
            info.interface = "SATA"
        if "device" in smart_data:
            d = smart_data.get("device", {})
            info.model = d.get("name") or info.model
            info.serial = d.get("serial") or info.serial
        if "model_name" in smart_data:
            info.model = smart_data["model_name"]
        if "serial_number" in smart_data:
            info.serial = smart_data["serial_number"]
        if "user_capacity" in smart_data:
            cap = smart_data["user_capacity"]
            if isinstance(cap, dict):
                info.capacity_gb = round(cap.get("bytes", 0) / 1e9, 1)
            elif isinstance(cap, list) and len(cap) >= 2:
                info.capacity_gb = round(cap[0] / 1e9, 1)

        # 2. Always ALSO try WMI Win32_DiskDrive (most reliable)
        try:
            from process_inspector import expand_env
            import subprocess, json as jsonmod
            ps = ("Get-CimInstance Win32_DiskDrive | Select-Object Model,SerialNumber,Firmware,Size,Status"
                  " | Select-Object -First 1 | ConvertTo-Json -Compress")
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=10)
            d = jsonmod.loads(r.stdout) if r.stdout.strip() else {}
            if not info.model:
                info.model = d.get("Model")
            if not info.serial:
                info.serial = d.get("SerialNumber")
            if not info.firmware:
                info.firmware = d.get("Firmware")
            if not info.capacity_gb and d.get("Size"):
                info.capacity_gb = round(int(d["Size"]) / 1e9, 1)
        except Exception as e:
            log.debug("WMI fallback failed: %s", e)

        # 3. Annotate honesty
        if info.model is None:
            info.model = "Could not read drive"
        if info.health_percent is None:
            info.health_percent = None  # explicit; UI shows "— not measured"
        if info.tbw_written_tb is not None and info.tbw_rated_tb is None:
            info.tbw_rated_tb = 600.0
            # Don't fake health_percent from TBW — too imprecise

        return info

    def get_all_drives(self) -> List[DriveInfo]:
        """Get info for all detected storage devices."""
        drives = []
        for dev in self.get_drives():
            dev_name = dev.get("name")
            if dev_name:
                try:
                    info = self.get_drive_info(dev_name)
                    drives.append(info)
                except Exception as e:
                    log.warning("Failed to read %s: %s", dev_name, e)
        return drives