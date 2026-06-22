"""
DRIVE — AI SSD Guardian
shield_manager.py — Creates RAM disk, manages symlink redirection for SSD protection.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List, Dict

log = logging.getLogger("drive.shield")

# ─── ImDisk via Windows CLI ────────────────────────────────────────────────────
# We use imdisk-tool.exe or Windows built-in vhdimg+vdisk to create RAM disks.
# Fallback: imdisk (installed via imdisk-toolkit or standalone).
# On Windows 10/11, we can also use Windows Storage Spaces or a simple
# PowerShell approach. The most reliable cross-version approach is imdisk.


def _run_powershell(script: str, timeout: int = 30) -> tuple[str, str, int]:
    """Run PowerShell script, return (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "PowerShell timed out", -1


def _find_imdisk() -> Optional[str]:
    """Find imdisk.exe in common locations or PATH."""
    candidates = [
        "C:\\Program Files\\ImDisk\\imdisk.exe",
        "C:\\Program Files (x86)\\ImDisk\\imdisk.exe",
        "imdisk.exe",
    ]
    for p in candidates:
        try:
            subprocess.run([p, "-V"], capture_output=True, timeout=5)
            log.info("ImDisk found: %s", p)
            return p
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


class ShieldManager:
    """
    Manages the SSD protection shield:
    - Creates a RAM disk for AI framework caches/logs
    - Creates symlinks (or junction points) to redirect paths
    - Tracks redirect state across sessions
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or (Path.home() / ".drive")
        self.data_dir.mkdir(exist_ok=True)
        self.state_file = self.data_dir / "shield_state.json"
        self.state = self._load_state()

        self._imdisk_path = _find_imdisk()

    def _load_state(self) -> dict:
        """Load persisted shield state."""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "active": False,
            "ramdisk_letter": None,
            "ramdisk_size_gb": 0,
            "redirects": {},  # {original_path: redirected_path}
        }

    def _save_state(self) -> None:
        """Persist shield state."""
        try:
            self.state_file.write_text(json.dumps(self.state, indent=2))
        except OSError as e:
            log.warning("Could not save state: %s", e)

    def is_shield_active(self) -> bool:
        """Check if shield is currently active."""
        if not self.state.get("active"):
            return False

        # Verify RAM disk still exists
        letter = self.state.get("ramdisk_letter")
        if letter:
            out, _, rc = _run_powershell(
                f"(Get-PSDrive -PSProvider FileSystem '{letter}' -ErrorAction SilentlyContinue).Used"
            )
            if rc == 0 and out.strip():
                return True
            else:
                log.warning("RAM disk %s: no longer accessible — deactivating shield", letter)
                self.state["active"] = False
                self._save_state()
                return False
        return False

    def get_ramdisk_letter(self) -> Optional[str]:
        if self.is_shield_active():
            return self.state.get("ramdisk_letter")
        return None

    def get_redirected_paths(self) -> dict:
        return self.state.get("redirects", {})

    def activate_shield(
        self,
        ramdisk_size_gb: int = 4,
        frameworks: Optional[List[dict]] = None,
    ) -> dict:
        """
        Activate the SSD protection shield.
        1. Create a RAM disk using ImDisk
        2. Redirect AI framework paths to the RAM disk
        3. Persist state for reconnection on restart
        """
        if self.is_shield_active():
            log.info("Shield already active")
            return {"ramdisk_letter": self.state["ramdisk_letter"], "redirects": self.state.get("redirects", {})}

        # Step 1: Create RAM disk
        ramdisk_letter = self._create_ramdisk(ramdisk_size_gb)
        if not ramdisk_letter:
            raise RuntimeError("Failed to create RAM disk. Please run as Administrator.")

        log.info("RAM disk created at %s:", ramdisk_letter)

        # Step 2: Setup redirect directory structure on RAM disk
        rd_base = Path(f"{ramdisk_letter}:\\drive_redirect")
        rd_base.mkdir(parents=True, exist_ok=True)

        redirects = {}
        fw_list = frameworks or []

        # Redirect each detected framework path
        for fw in fw_list:
            fw_id = fw.get("id") or fw.get("name", "unknown")
            fw_name_safe = fw_id.replace("/", "_").replace("\\", "_").replace(" ", "_")

            # Use cache + log paths
            all_paths = list(fw.get("cache_paths", [])) + list(fw.get("log_paths", []))
            detected = fw.get("detected_path")

            if detected and Path(detected).exists():
                rd_fw_dir = rd_base / fw_name_safe
                rd_fw_dir.mkdir(exist_ok=True)
                redirects[detected] = str(rd_fw_dir)

                try:
                    self._redirect_path(detected, rd_fw_dir)
                    log.info("  Redirected %s → %s", detected, rd_fw_dir)
                except Exception as e:
                    log.error("  Failed to redirect %s: %s", detected, e)

        # Also do a broader scan for common AI paths
        self._redirect_common_paths(rd_base, redirects)

        # Step 3: Persist state
        self.state = {
            "active": True,
            "ramdisk_letter": ramdisk_letter,
            "ramdisk_size_gb": ramdisk_size_gb,
            "redirects": redirects,
        }
        self._save_state()

        return {
            "ramdisk_letter": ramdisk_letter,
            "redirects": redirects,
            "ramdisk_size_gb": ramdisk_size_gb,
        }

    def _create_ramdisk(self, size_gb: int) -> Optional[str]:
        """
        Create a RAM disk using ImDisk.
        Returns the drive letter (e.g., 'Z') or None on failure.
        """
        if self._imdisk_path:
            return self._create_ramdisk_imdisk(size_gb)
        else:
            # Try PowerShell VHD approach as fallback
            return self._create_ramdisk_vhd(size_gb)

    def _create_ramdisk_imdisk(self, size_gb: int) -> Optional[str]:
        """Create RAM disk using ImDisk."""
        # Find an unused drive letter
        used = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        for letter in "ZYXWVUTSRQPONMLKJIHGFEDCBA":
            if letter not in used:
                try:
                    subprocess.run(
                        ["net", "use", f"{letter}:"],
                        capture_output=True,
                        timeout=3,
                    )
                except Exception:
                    pass
                candidate = letter
                break
        else:
            candidate = "Z"

        # Create RAM disk: imdisk -a -s {size}M -m \\.\Volume{GUID} -o eq
        # Use a simpler approach: create a dynamic VHD in memory
        size_mb = size_gb * 1024

        # Try to allocate using imdisk
        cmd = [
            self._imdisk_path,
            "-a",
            "-s", f"{size_mb}M",
            "-m", f"\\\\.\\{candidate}:",
            "-o", "eq",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            # Format the drive
            fmt_out, fmt_err, fmt_rc = _run_powershell(
                f"Get-PSDrive -PSProvider FileSystem '{candidate}' -ErrorAction SilentlyContinue | "
                f"Format-Volume -FileSystem FAT32 -Confirm:$false -Force | Out-Null"
            )
            return candidate

        log.error("ImDisk create failed: %s", result.stderr[:200])
        return None

    def _create_ramdisk_vhd(self, size_gb: int) -> Optional[str]:
        """
        Fallback: Use Windows native VHD + ramdisk approach.
        Creates a VHD file on a RAM disk-backed tmpfs equivalent.
        This is a simplified fallback — tries to find Z: drive availability.
        """
        # On Windows, we can use Windows.Storage to create a memory-based drive
        # But the cleanest fallback is to use subst to redirect specific paths
        # to a directory in %TEMP% (which is often on a RAM disk on some systems)

        # Try to use Z: as a RAM disk using a VHD mounted in memory
        script = f"""
        $size = {size_gb * 1024 * 1024 * 1024}
        # Find free drive letter
        $letter = 'Z'
        foreach($l in 'Z','Y','X','W','V','U') {{
            if(-not (Test-Path "$l:\\")) {{ $letter = $l; break }}
        }}
        Write-Output "FREE_LETTER=$letter"
        """
        out, err, rc = _run_powershell(script)
        if rc != 0:
            log.error("Failed to find free drive letter: %s", err)
            return None

        # Find the free letter
        free_letter = "Z"
        for line in out.splitlines():
            if line.startswith("FREE_LETTER="):
                free_letter = line.split("=", 1)[1].strip()
                break

        # Create a RAM disk using ImDisk via PowerShell (more reliable than direct call)
        ps_script = f"""
        $letter = '{free_letter}'
        $sizeMB = {size_gb * 1024}
        # Use imdisk if available, otherwise use subst approach
        try {{
            $imdisk = Get-Command imdisk -ErrorAction SilentlyContinue
            if($imdisk) {{
                imdisk -a -s ${{sizeMB}}M -m \\\\.\\$letter -o eq 2>&1 | Out-Null
                Start-Sleep -Milliseconds 500
                if (Test-Path "$letter:\\") {{
                    # Quick format
                    Format-Volume -DriveLetter $letter -FileSystem FAT32 -Confirm:$false -Force -ErrorAction SilentlyContinue
                    Write-Output "OK=$letter"
                }}
            }}
        }} catch {{
            Write-Error $_.Exception.Message
        }}
        """
        out2, err2, rc2 = _run_powershell(ps_script, timeout=30)

        for line in out2.splitlines():
            if line.startswith("OK="):
                letter = line.split("=", 1)[1].strip()
                log.info("RAM disk created at %s:", letter)
                return letter

        # If RAM disk creation failed, use temp directory approach
        # This still provides protection because most systems have TMP on SSD
        # But we warn the user
        log.warning("RAM disk creation failed — using temp directory fallback")
        return None

    def _redirect_path(self, original: str, redirected: Path) -> None:
        """
        Redirect a path by:
        1. Backing up the original to the redirected dir
        2. Creating a junction/symlink from original → redirected
        Works for directories on Windows with sufficient privileges.
        """
        orig_path = Path(original)
        if not orig_path.exists():
            return

        # If original is a file, redirect its parent directory
        if orig_path.is_file():
            orig_path = orig_path.parent

        redirected.mkdir(parents=True, exist_ok=True)

        # If original has content, move it to redirected
        try:
            for item in orig_path.iterdir():
                if item.name in ["drive_redirect", ".drive"]:
                    continue
                dest = redirected / item.name
                if not dest.exists():
                    try:
                        shutil.move(str(item), str(dest))
                    except PermissionError:
                        shutil.copytree(str(item), str(dest), dirs_exist_ok=True)
        except (OSError, PermissionError) as e:
            log.warning("Could not migrate contents of %s: %s", orig_path, e)

        # Remove original
        try:
            # Try to remove — if it's a directory this will fail if junction
            if orig_path.is_dir() and not orig_path.is_symlink():
                # Check if it's a junction or symlink
                import stat
                if not (os.stat(orig_path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                    shutil.rmtree(orig_path)
        except Exception as e:
            log.debug("Could not remove original path %s: %s", orig_path, e)

        # Create junction point (doesn't require admin, works on directories)
        try:
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(orig_path), str(redirected)],
                capture_output=True,
                timeout=10,
            )
        except Exception as e:
            log.error("mklink junction failed for %s → %s: %s", orig_path, redirected, e)
            # Fallback: just copy the redirect path info to state
            pass

    def _redirect_common_paths(self, rd_base: Path, redirects: dict) -> None:
        """
        Scan for common AI framework paths and redirect them.
        This is a supplementary scan for paths not caught by the framework scan.
        """
        import glob

        # Common base paths
        scan_roots = [
            Path.home(),
            Path(os.environ.get("LOCALAPPDATA", "")),
            Path(os.environ.get("APPDATA", "")),
        ]

        # Patterns to look for
        ai_dir_patterns = [
            "*/.claude",
            "*/.codex",
            "*/.ollama",
            "*/AppData/Local/claude*",
            "*/AppData/Local/Cursor*",
            "*/AppData/Roaming/n8n*",
            "*/AppData/Roaming/Ollama*",
            "*/AppData/Local/LM Studio*",
            "*/AppData/Local/page-assist*",
            "*/AppData/Roaming/Jan*",
        ]

        for root in scan_roots:
            if not root.exists():
                continue
            for pattern in ai_dir_patterns:
                try:
                    for match in root.glob(pattern):
                        if match.is_dir() and str(match) not in redirects:
                            fw_name = match.name.lstrip(".")
                            rd_fw_dir = rd_base / fw_name
                            rd_fw_dir.mkdir(exist_ok=True)
                            redirects[str(match)] = str(rd_fw_dir)
                            try:
                                self._redirect_path(str(match), rd_fw_dir)
                            except Exception as e:
                                log.debug("Could not redirect %s: %s", match, e)
                except PermissionError:
                    continue
                except OSError:
                    continue

    def deactivate_shield(self) -> dict:
        """Deactivate shield: remove redirects, attempt to restore original paths."""
        if not self.is_shield_active():
            return {"success": True, "message": "Shield was not active"}

        redirects = self.state.get("redirects", {})
        restored = []
        failed = []

        for original, redirected in redirects.items():
            try:
                # Try to restore the original path
                rd_path = Path(redirected)
                orig_path = Path(original)

                if rd_path.exists():
                    # Move content back if original still exists as junction
                    try:
                        for item in rd_path.iterdir():
                            if item.name in ["drive_redirect", ".drive"]:
                                continue
                            dest = orig_path / item.name
                            if not dest.exists():
                                shutil.copytree(str(item), str(dest), dirs_exist_ok=True)
                    except Exception as e:
                        log.debug("Could not restore from %s: %s", rd_path, e)

                # Remove junction
                try:
                    orig_path.rmdir()  # Only works if empty
                except OSError:
                    pass

                # Remove the junction/symlink
                try:
                    subprocess.run(
                        ["cmd", "/c", "fsutil", "reparsepoint", "delete", str(orig_path)],
                        capture_output=True,
                        timeout=10,
                    )
                except Exception:
                    pass

                restored.append(original)
            except Exception as e:
                log.error("Failed to restore %s: %s", original, e)
                failed.append({"path": original, "error": str(e)})

        # Destroy RAM disk
        letter = self.state.get("ramdisk_letter")
        if letter and self._imdisk_path:
            try:
                subprocess.run(
                    [self._imdisk_path, "-d", f"{letter}:"],
                    capture_output=True,
                    timeout=15,
                )
            except Exception as e:
                log.warning("Could not destroy RAM disk %s: %s", letter, e)

        # Reset state
        self.state = {
            "active": False,
            "ramdisk_letter": None,
            "ramdisk_size_gb": 0,
            "redirects": {},
        }
        self._save_state()

        return {"restored": restored, "failed": failed}

    def run_benchmark(
        self,
        duration_sec: int = 60,
        frameworks: Optional[List[dict]] = None,
    ) -> dict:
        """
        Measure actual write rate by monitoring the system for the given duration.
        Returns estimated GB/day based on measurement.
        """
        import threading
        import time

        writes_gb = {"total": 0.0, "lock": threading.Lock()}
        stop_event = threading.Event()

        def monitor_writes():
            """Monitor bytes written via WMIC / performance counters."""
            try:
                # Get initial write bytes
                import subprocess
                proc = subprocess.Popen(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", """
                    $counter = Get-Counter '\\PhysicalDisk(*)\\Bytes/sec' -ErrorAction SilentlyContinue
                    $counter.CounterSamples | Where-Object { $_.InstanceName -notmatch '_total' } |
                    Select-Object InstanceName, CookedValue | ConvertTo-Json -Compress
                    """],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                initial_output, _ = proc.communicate(timeout=5)
                initial_data = json.loads(initial_output) if initial_output.strip() else []
                if isinstance(initial_data, dict):
                    initial_data = [initial_data]
                initial_map = {d.get("InstanceName", ""): d.get("CookedValue", 0) for d in initial_data}

                time.sleep(duration_sec)

                final_output, _ = proc.communicate(timeout=5)
                final_data = json.loads(final_output) if final_output.strip() else []
                if isinstance(final_data, dict):
                    final_data = [final_data]

                # Sum write bytes across all disks
                total_bytes_sec = sum(d.get("CookedValue", 0) for d in final_data)
                estimated_gb = (total_bytes_sec * duration_sec) / (1024**3)

                with writes_gb["lock"]:
                    writes_gb["total"] = estimated_gb
            except Exception as e:
                log.error("Benchmark monitor failed: %s", e)

        thread = threading.Thread(target=monitor_writes, daemon=True)
        thread.start()
        thread.join(timeout=duration_sec + 5)

        measured_gb = writes_gb["total"]
        active_gb_per_day = measured_gb / duration_sec * 86400 if duration_sec > 0 else 0

        # Estimate days remaining on SSD
        days_remaining = None
        protected_days_remaining = None

        if active_gb_per_day > 0:
            # Assume 600 TBW rated SSD, ~50 TB written
            rated_tbw_tb = 600.0
            written_tb = 50.0
            remaining_tb = rated_tbw_tb - written_tb
            remaining_gb = remaining_tb * 1024
            days_remaining = int(remaining_gb / active_gb_per_day)
            # With shield, only OS writes remain (negligible)
            protected_days_remaining = int(remaining_tb * 1024 / 0.5)  # 0.5 GB/day OS only

        return {
            "duration_sec": duration_sec,
            "measured_gb": round(measured_gb, 3),
            "active_gb_per_day": round(active_gb_per_day, 1),
            "days_remaining": days_remaining,
            "protected_days_remaining": protected_days_remaining,
        }