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
        Read SMART data for a specific device or the first available drive.
        Returns DriveInfo with all available health metrics.
        """
        if device is None:
            # Find first available device
            drives = self.get_drives()
            if drives:
                device = drives[0].get("name") or drives[0].get("info", {}).get("name")
            if not device:
                log.warning("No drives detected — returning empty DriveInfo")
                return DriveInfo(model="No drive detected")

        info = DriveInfo()

        try:
            # NVMe path
            data = self._run_smartctl(["-j", "-a", device])

            if "nvme_smart_health_information_log" in data:
                nvme = data["nvme_smart_health_information_log"]
                info.temperature_c = nvme.get("temperature")
                info.power_on_hours = nvme.get("power_on_hours")
                info.power_cycles = nvme.get("power_cycles")

                # NVMe bytes written — convert to TB
                bytes_written = nvme.get("data_units_written", 0)
                if isinstance(bytes_written, list) and len(bytes_written) >= 2:
                    bytes_written = bytes_written[0]  # First value
                info.tbw_written_tb = round(bytes_written * 512 / 1_000_000, 3)

                spare = nvme.get("available_spare")
                if spare is not None:
                    info.spare_remaining_pct = int(spare)
                    info.health_percent = int(spare)

                info.interface = "NVMe"

            # ATA/SATA path
            if "ata_smart_attributes" in data:
                ata = data["ata_smart_attributes"]
                info.model = ata.get("model", info.model)
                info.serial = ata.get("serial", info.serial)
                info.firmware = ata.get("firmware", info.firmware)

                # Parse SMART attributes table
                table = ata.get("table", [])
                for attr in table:
                    id_num = attr.get("id")
                    name = attr.get("name", "").lower()
                    value = attr.get("value")
                    worst = attr.get("worst")
                    thresh = attr.get("thresh")
                    raw = attr.get("raw", {}).get("string", "").strip()

                    if id_num == 9:   # Power-On Hours
                        info.power_on_hours = int(raw) if raw.isdigit() else value
                    elif id_num == 12:  # Power Cycle Count
                        info.power_cycles = int(raw) if raw.isdigit() else value
                    elif id_num == 177:  # Wear Leveling Count (SSD)
                        info.wear_leveling = value
                        if value and thresh and thresh > 0:
                            info.health_percent = int((value / thresh) * 100)
                    elif id_num == 232:  # Endurance Remaining (Intel)
                        info.health_percent = value
                    elif id_num == 233:  # Media Wear Remaining (Samsung)
                        info.health_percent = value
                    elif id_num == 241:  # Total LBAs Written (Western Digital)
                        if raw:
                            try:
                                parts = raw.split()
                                val = int(parts[0], 16) if parts else 0
                                info.tbw_written_tb = round(val * 512 / 1e12, 3)
                            except Exception:
                                pass
                    elif id_num == 242:  # Total LBAs Read
                        pass  # Not TBW but useful for completeness

                info.interface = "SATA"

            # Common fields from info section
            if "device" in data:
                dev_info = data.get("device", {})
                info.model = dev_info.get("name") or info.model
                info.serial = dev_info.get("serial") or info.serial

            if "model_name" in data:
                info.model = data["model_name"]
            if "serial_number" in data:
                info.serial = data["serial_number"]
            if "user_capacity" in data:
                cap = data["user_capacity"]
                if isinstance(cap, dict):
                    info.capacity_gb = round(cap.get("bytes", 0) / 1e9, 1)
                elif isinstance(cap, list) and len(cap) >= 2:
                    info.capacity_gb = round(cap[0] / 1e9, 1)

            # Fallback: parse from model name
            if not info.model:
                info.model = device

            # If we still have no health estimate, estimate from TBW
            if info.health_percent is None and info.tbw_written_tb is not None:
                # Assume typical consumer SSD: 600 TBW rated
                rated = 600.0
                info.tbw_rated_tb = rated
                info.health_percent = round(
                    max(0, min(100, (1 - info.tbw_written_tb / rated) * 100)), 1
                )

        except Exception as e:
            log.error("Failed to read SMART data: %s", e)
            # Return what we have
            if not info.model:
                info.model = device or "Unknown"

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