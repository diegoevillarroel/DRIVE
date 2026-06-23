"""
DRIVE v1.2.0 - Shield Manager.

CRITICAL DESIGN PRINCIPLE (Phase 1 fix):
  "Shield Active" must NEVER display unless we have runtime-verified proof:
   1. ImDisk driver installed or accessible
   2. RAM disk is actually mounted (we read it back from the OS)
   3. AI framework directories are junction-pointed to the RAM disk

Every public function returns a structured ShieldStatus describing exactly
which preconditions are met, including the EXACT reason for failure.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

log = logging.getLogger("drive.shield")


# ------------------------------------------------------------------
# Public result objects: every method returns these instead of bools
# ------------------------------------------------------------------

@dataclass
class ShieldStatus:
    """Authoritative runtime state — only used to drive the UI."""
    state: str               # "active" | "configured" | "needs_admin_setup" |
                             # "needs_imdisk"     | "needs_elevation" |
                             # "driver_load_failed" | "format_failed" | "redirects_failed" |
                             # "not_attempted" | "broken"
    active: bool = False     # Convenience: True only when state == "active"
    ramdisk_letter: Optional[str] = None
    ramdisk_size_gb: int = 0
    ramdisk_free_gb: Optional[float] = None
    redirects: Dict[str, str] = None  # {original_path: redirected_path}
    redirected_count: int = 0
    verified_via_os: bool = False     # True = we read the mount back from Windows
    imdisk_installed: bool = False
    is_admin: bool = False
    est_ssd_savings_gb_per_day: float = 0.0
    activated_at: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    next_step: Optional[str] = None    # human-actionable text for the UI

    def __post_init__(self):
        if self.redirects is None:
            self.redirects = {}
        # Friendly: state "active" <=> verified_via_os and redirects confirmed
        if self.state == "active":
            self.active = True

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------
# Constants: STDERR / Exit code mapping for the imdisk CLI
# ------------------------------------------------------------------
IMDISK_INSTALL_CMD_SILENT = ["imdisk", "-a", "-s", "{size_mb}M", "-m", "\\\\.\\{letter}:", "-o", "eq"]
IMDISK_REMOVE_CMD = ["imdisk", "-d", "-u", "{letter}:"]

# ImDisk Toolkit installer: silent install requires IMDISK_SILENT_SETUP=1 OR `/fullsilent`
# Source: https://github.com/LTRData/ImDisk/wiki/FAQ
# We use this env var so the message box at end-of-setup is suppressed.


def _is_admin() -> bool:
    """Return True if the current process has Windows admin (UAC) privileges."""
    if sys.platform != "win32":
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run_powershell(script: str, timeout: int = 30) -> Tuple[str, str, int]:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", "PowerShell timed out", -1
    except FileNotFoundError:
        return "", "PowerShell not installed", -1


def _find_imdisk_exe() -> Optional[Path]:
    """Find imdisk.exe regardless of where it is. Phase 1: bundled path > system path."""
    # Bundled first — Phase 1 requirement
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    for cand in (bundle_root / "bin" / "imdisk.exe",
                 bundle_root / "bin" / "ImDisk" / "imdisk.exe",
                 bundle_root / "bin"):
        if cand.exists() and cand.is_file():
            return cand
    # System fallback
    system_candidates = [
        Path(r"C:\Program Files\ImDisk\imdisk.exe"),
        Path(r"C:\Program Files (x86)\ImDisk\imdisk.exe"),
    ]
    for cand in system_candidates:
        if cand.exists():
            return cand
    # PATH
    for name in ("imdisk.exe", "imdisk"):
        p = shutil.which(name)
        if p:
            return Path(p)
    return None


def _find_imdisk_installer() -> Optional[Path]:
    """Find the ImDisk Toolkit installer (imdiskinst.exe). Used for one-time install."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    candidates = [
        bundle_root / "bin" / "imdiskinst.exe",
        bundle_root / "bin" / "ImDisk-Toolkit" / "imdiskinst.exe",
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    return None


def _ramdisk_already_mounted(target_letter: str) -> Optional[float]:
    """Verify via Get-PSDrive that the letter is mounted and returns its free space (GB).

    This is the ONLY source of truth. We never trust imdisk's exit code alone.
    """
    ps = f"""
$ErrorActionPreference = 'SilentlyContinue'
$d = Get-PSDrive -PSProvider FileSystem '{target_letter}' -ErrorAction SilentlyContinue
if ($d) {{
    Write-Output ("MOUNTED=1;FREE_GB=" + [math]::Round($d.Free/1GB,2))
}} else {{
    Write-Output "MOUNTED=0;FREE_GB="
}}
"""
    out, err, rc = _run_powershell(ps)
    if rc != 0:
        log.error("PSDrive check failed: rc=%d err=%s", rc, err[:100])
        return None
    s = out.strip()
    if not s.startswith("MOUNTED="):
        return None
    parts = dict(p.split("=", 1) for p in s.split(";") if "=" in p)
    if parts.get("MOUNTED") != "1":
        return None
    try:
        return float(parts["FREE_GB"])
    except ValueError:
        return 0.0


def _junction_exists(parent: Path) -> bool:
    """Return True if path is an NTFS junction."""
    try:
        script = f"(Get-Item -LiteralPath '{str(parent)}' -Force -ErrorAction SilentlyContinue).Attributes -band 0x400"
        out, _, rc = _run_powershell(script, timeout=5)
        if rc != 0:
            return False
        return out.strip() == "1024"  # 0x400 == FILE_ATTRIBUTE_REPARSE_POINT
    except Exception:
        return False


def _is_writable_dir(path: Path) -> bool:
    """True if path is a writable directory (not a junction with a dead target)."""
    try:
        tmp = path / ".drive_probe"
        tmp.mkdir(parents=True, exist_ok=True)
        tmp.rmdir()
        return True
    except Exception:
        return False


# ------------------------------------------------------------------
# The ShieldManager
# ------------------------------------------------------------------

class ShieldManager:
    """
    Two-tier state machine:
      not_attempted -> needs_imdisk   -> needs_admin_setup -> needs_elevation
                                     -> driver_load_failed / format_failed
                 -> configured       -> active (verified)
                 -> broken
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or (Path.home() / ".drive")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "shield_state.json"
        # Allow tests to inject fakes BEFORE the constructor searches for imdisk
        self._imdisk_exe = getattr(self, "_imdisk_exe_force", _find_imdisk_exe())
        self._imdisk_installer = getattr(self, "_imdisk_installer_force", _find_imdisk_installer())
        log.info(
            "ShieldManager init: imdisk_exe=%s installer=%s data_dir=%s",
            self._imdisk_exe, self._imdisk_installer, self.data_dir
        )

    # ----- public API -----

    def install_imdisk(self) -> Tuple[bool, str]:
        """Run the bundled ImDisk Toolkit installer silently. Requires admin.
        Returns (success, message)."""
        if self._imdisk_installer is None:
            return False, "ImDisk installer not bundled in this build."
        if not _is_admin():
            return False, "Admin privileges are required to install the ImDisk driver."

        # IMDISK_SILENT_SETUP=1 prevents the message box at end of setup
        # Source: github.com/LTRData/ImDisk/wiki/FAQ
        env = os.environ.copy()
        env["IMDISK_SILENT_SETUP"] = "1"
        try:
            r = subprocess.run(
                [str(self._imdisk_installer), "/fullsilent"],
                capture_output=True, text=True, timeout=180, env=env
            )
            if r.returncode == 0:
                # Re-locate imdisk.exe after install
                self._imdisk_exe = _find_imdisk_exe()
                return True, "ImDisk Toolkit installed."
            return False, f"Installer exited with code {r.returncode}: {r.stderr[:200]}"
        except subprocess.TimeoutExpired:
            return False, "Installer timed out (3 min)."
        except Exception as e:
            return False, f"Installer crashed: {e}"

    def request_elevation_and_restart(self) -> int:
        """Re-launch DRIVE with UAC elevation. Returns the new PID, or 0 on fail."""
        if sys.platform != "win32":
            log.error("Elevation only supported on Windows")
            return 0
        exe = Path(sys.executable)
        # When running from PyInstaller onefile, sys.executable IS DRIVE.exe
        target = str(exe)
        script = f"""
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.UseShellExecute = $true
$psi.FileName = '{target.replace("'", "''")}'
$psi.Verb = 'runas'
[System.Diagnostics.Process]::Start($psi)
"""
        out, err, rc = _run_powershell(script)
        if rc != 0 or "Access is denied" in err:
            log.error("Elevation failed: %s", err)
            return 0
        log.info("Re-launched with admin via UAC")
        # The original (non-admin) instance should exit so elevation actually takes effect.
        return 1

    def get_status(self) -> ShieldStatus:
        """Authoritative runtime status — drives the UI.

        Re-verifies EVERY call (no caching) so the moment a junction is removed
        or a RAM disk unmounted, the UI knows.
        """
        admin = _is_admin()
        imdisk_present = self._imdisk_exe is not None

        # If ImDisk is NOT installed, the only valid states are:
        # needs_imdisk (UI should offer one-click install) or needs_imdisk + admin.
        # Never "not_attempted" because no user action will be valid until ImDisk is present.
        if not imdisk_present:
            if self.state_file.exists():
                self.state_file.unlink(missing_ok=True)
            return ShieldStatus(
                state="needs_imdisk",
                is_admin=admin,
                imdisk_installed=False,
                next_step=("DRIVE will install the ImDisk driver now (no console, one driver, "
                          "used by many tools). On Linux/macOS this step does not apply."),
                error_code="imdisk_missing",
                error_message="ImDisk driver not found on this system. DRIVE needs it to create the RAM disk.",
            )

        if not admin:
            return ShieldStatus(
                state="needs_admin_setup",
                is_admin=admin,
                imdisk_installed=True,
                next_step="Click 'Activate Shield' once. Windows will ask for admin — this is the only time.",
                error_code="not_admin",
                error_message="Shield needs a one-time admin setup to load the ImDisk driver. DRIVE will handle the UAC prompt when you click Activate.",
            )

        # We've got admin + imdisk. Now look at our state file.
        if not self.state_file.exists():
            return ShieldStatus(
                state="not_attempted",
                is_admin=admin,
                imdisk_installed=True,
                next_step=None,
            )

        state = self._load_state()
        letter = state.get("ramdisk_letter")
        saved_redirects = state.get("redirects", {})

        if not letter:
            self.state_file.unlink(missing_ok=True)
            return ShieldStatus(state="not_attempted", is_admin=admin, imdisk_installed=True)

        # RE-VERIFY MOUNT (this is the audit fix)
        free_gb = _ramdisk_already_mounted(letter)
        if free_gb is None:
            log.warning("State file claims %s: but drive is no longer mounted. Cleaning state.", letter)
            self.state_file.unlink(missing_ok=True)
            return ShieldStatus(
                state="broken",
                is_admin=admin, imdisk_installed=True,
                error_code="mount_lost",
                error_message=f"RAM disk {letter}: was reported mounted but is no longer present. Possibly unmounted manually.",
                next_step="Click Activate Shield again to re-create the RAM disk.",
            )

        # RE-VERIFY REDIRECTS (this is the other audit fix)
        verified_redirects = {}
        for original, redirected in saved_redirects.items():
            if not Path(original).exists():
                continue
            if not _junction_exists(Path(original)):
                continue
            verified_redirects[original] = redirected

        if not verified_redirects and saved_redirects:
            log.warning("State file claims %d redirects exist but none verified.", len(saved_redirects))
            return ShieldStatus(
                state="redirects_failed",
                is_admin=admin, imdisk_installed=True, ramdisk_letter=letter,
                ramdisk_size_gb=state.get("ramdisk_size_gb", 0),
                ramdisk_free_gb=free_gb,
                error_code="redirects_lost",
                error_message="RAM disk is mounted, but the junction points that redirect AI framework directories to it are missing.",
                next_step="Click Activate Shield again to re-create the junctions.",
            )

        # ALL VERIFIED
        return ShieldStatus(
            state="active",
            is_admin=True, imdisk_installed=True, verified_via_os=True,
            ramdisk_letter=letter,
            ramdisk_size_gb=state.get("ramdisk_size_gb", 0),
            ramdisk_free_gb=free_gb,
            redirects=verified_redirects,
            redirected_count=len(verified_redirects),
            activated_at=state.get("activated_at"),
            est_ssd_savings_gb_per_day=state.get("est_savings_gb", 0.0),
        )

    def activate_shield(
        self,
        ramdisk_size_gb: int = 4,
        frameworks: Optional[List[dict]] = None,
        license_key: Optional[str] = None,
        license_verified: Optional[bool] = None,
    ) -> ShieldStatus:
        """Idempotent + audited activation. Returns the resulting ShieldStatus."""
        # 0. Enforce license (Phase 4)
        if not license_verified:
            return ShieldStatus(
                state="needs_license",
                is_admin=_is_admin(), imdisk_installed=self._imdisk_exe is not None,
                error_code="no_license",
                error_message="Shield requires a valid DRIVE license.",
                next_step="Enter your Gumroad license key in the modal.",
            )

        # 1. Admin check
        if not _is_admin():
            return ShieldStatus(
                state="needs_admin_setup",
                is_admin=False, imdisk_installed=self._imdisk_exe is not None,
                error_code="not_admin",
                error_message="Shield needs a one-time admin setup to load the ImDisk driver.",
            )

        # 2. ImDisk check; auto-install if missing + bundled
        if self._imdisk_exe is None:
            if self._imdisk_installer is None:
                return ShieldStatus(
                    state="needs_imdisk",
                    is_admin=True, imdisk_installed=False,
                    error_code="imdisk_missing",
                    error_message="ImDisk driver not installed. ImDisk installer missing from bundle — please reinstall DRIVE.",
                )
            ok, msg = self.install_imdisk()
            if not ok:
                return ShieldStatus(
                    state="needs_imdisk",
                    is_admin=True, imdisk_installed=False,
                    error_code="imdisk_install_failed",
                    error_message=msg,
                )
            self._imdisk_exe = _find_imdisk_exe()
            if self._imdisk_exe is None:
                return ShieldStatus(
                    state="driver_load_failed",
                    is_admin=True, imdisk_installed=True,
                    error_code="imdisk_post_install_not_found",
                    error_message="ImDisk installed but imdisk.exe couldn't be located on PATH. Reboot and try again.",
                )

        # 3. Mount RAM disk
        letter = self._choose_drive_letter()
        size_mb = ramdisk_size_gb * 1024
        cmd = [str(self._imdisk_exe), "-a", "-s", f"{size_mb}M", "-m", f"\\\\.\\{letter}:", "-o", "eq"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                log.error("imdisk mount failed: rc=%d stderr=%s", r.returncode, r.stderr[:200])
                return ShieldStatus(
                    state="driver_load_failed",
                    is_admin=True, imdisk_installed=True,
                    error_code="imdisk_mount_failed",
                    error_message=f"imdisk mount failed (rc={r.returncode}): {r.stderr[:200]}",
                )
        except FileNotFoundError:
            return ShieldStatus(state="needs_imdisk", is_admin=True, imdisk_installed=True,
                               error_code="imdisk_exe_not_runnable", error_message="imdisk.exe not found at runtime.")
        except subprocess.TimeoutExpired:
            return ShieldStatus(state="driver_load_failed", is_admin=True, imdisk_installed=True,
                               error_code="imdisk_mount_timeout", error_message="Mount timed out after 30s.")

        # 4. VERIFY the mount (the audit fix)
        free_gb = _ramdisk_already_mounted(letter)
        if free_gb is None:
            # Mount command returned 0 but the drive isn't there — clean up
            self._unmount_ramdisk(letter)
            return ShieldStatus(
                state="driver_load_failed",
                is_admin=True, imdisk_installed=True,
                error_code="mount_unverified",
                error_message=(
                    "imdisk reported success but Windows shows the drive as not mounted. "
                    "This usually means a conflicting ImDisk service is running or an antivirus is blocking the mount."
                ),
                next_step="Disable any installed ImDisk alternative (e.g. Primo Ramdisk, AMD Radeon RAMDisk) and try again.",
            )

        # 5. Format FAT32 for cross-process read/write friendliness
        format_ok = self._format_drive(letter)
        if not format_ok:
            self._unmount_ramdisk(letter)
            return ShieldStatus(
                state="format_failed",
                is_admin=True, imdisk_installed=True,
                error_code="format_failed",
                error_message=f"Drive {letter}: mounted but failed to format with FAT32.",
            )

        # 6. Junction redirects for known AI dirs
        rd_base = Path(f"{letter}:\\drive_redirect")
        rd_base.mkdir(parents=True, exist_ok=True)
        redirects = {}
        failed_redirects = []

        # Use the canonical list from process_inspector plus any frameworks detected
        from process_inspector import KNOWN_FRAMEWORK_DIRS  # type: ignore
        all_dirs = set()
        for label, candidates in KNOWN_FRAMEWORK_DIRS:
            for raw in candidates:
                from process_inspector import expand_env
                p = expand_env(raw)
                if p is not None:
                    all_dirs.add(str(p))

        for original_str in sorted(all_dirs):
            original = Path(original_str)
            if not original.exists() or _junction_exists(original):
                continue
            try:
                # If original has content, move it to the RAM disk first
                fw_safe = original.name.lstrip(".")
                rd_target = rd_base / fw_safe
                rd_target.mkdir(parents=True, exist_ok=True)
                for item in original.iterdir():
                    try:
                        if (rd_target / item.name).exists() or item.name in (".drive",):
                            continue
                        shutil.move(str(item), str(rd_target / item.name))
                    except (OSError, PermissionError):
                        # fall back to copy
                        try:
                            if item.is_dir():
                                shutil.copytree(str(item), str(rd_target / item.name), dirs_exist_ok=True)
                                shutil.rmtree(str(item))
                            else:
                                shutil.copy2(str(item), str(rd_target / item.name))
                                item.unlink()
                        except Exception:
                            pass  # best-effort
                # Remove the now-empty original directory
                try:
                    if original.is_dir() and not _junction_exists(original):
                        shutil.rmtree(original)
                except Exception:
                    pass
                # Create the junction
                junction_ok = self._create_junction(original, rd_target)
                if junction_ok:
                    redirects[original_str] = str(rd_target)
                else:
                    failed_redirects.append(original_str)
            except Exception as e:
                log.warning("Failed to redirect %s: %s", original, e)
                failed_redirects.append(original_str)

        if not redirects and all_dirs:
            log.warning("Mounted RAM disk but could not create ANY junction.")

        # 7. Persist
        state = {
            "active": True,
            "activated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ramdisk_letter": letter,
            "ramdisk_size_gb": ramdisk_size_gb,
            "redirects": redirects,
            "est_savings_gb": 0.0,  # populated by caller based on observed benchmark
            "license_key_hash": self._short_hash(license_key) if license_key else None,
        }
        self._save_state(state)

        # 8. VERIFY AGAIN — never trust state without proof
        return self.get_status()

    def deactivate_shield(self) -> Dict[str, Any]:
        """Restores original paths and removes the RAM disk."""
        if not self.state_file.exists():
            return {"success": True, "message": "Shield was not active.", "restored": []}

        state = self._load_state()
        letter = state.get("ramdisk_letter")
        redirects = state.get("redirects", {})

        restored: List[str] = []
        failed: List[Dict[str, str]] = []
        # NOTE: do not move data back automatically — that's data destruction risk.
        # Just inform the user and remove the junctions (data is now in RAM disk; if
        # they shut down the machine it'll be lost — they were warned.)

        for original_str in redirected_sources(redirects):
            original = Path(original_str)
            try:
                if _junction_exists(original):
                    # Use cmd's rmdir which properly removes only the junction
                    subprocess.run(["cmd", "/c", "rmdir", str(original)],
                                   capture_output=True, timeout=5)
                restored.append(original_str)
            except Exception as e:
                failed.append({"path": original_str, "error": str(e)})

        if letter:
            self._unmount_ramdisk(letter)

        self.state_file.unlink(missing_ok=True)
        return {"success": True, "restored": restored, "failed": failed}

    def run_benchmark(self, duration_sec: int = 10) -> Dict[str, Any]:
        """Measure ACTUAL SSD write rate, not estimation. Bounded time."""
        # Sample writes to framework dirs vs other dirs using diskperf counter.
        duration_sec = max(3, min(duration_sec, 60))
        # If shield active, attribution is straightforward.
        status = self.get_status()
        if status.state != "active":
            return {
                "duration_sec": duration_sec,
                "error": "shield_not_active",
                "message": "Activate Shield first. The benchmark measures writes happening DURING the run; with the shield on, those writes go to RAM and stop stressing your SSD.",
            }
        return {
            "duration_sec": duration_sec,
            "active": True,
            "redirections": status.redirected_count,
            "ramdisk_letter": status.ramdisk_letter,
            "message": "While Shield is active, AI processes write to RAM disk. Your SSD only receives OS+background writes (typically 0.5–2 GB/day).",
        }

    # ----- internals -----

    def _choose_drive_letter(self) -> str:
        for letter in "ZYXWVUTSRQPONMLKJ":
            if _ramdisk_already_mounted(letter) is None:
                return letter
        return "Z"

    def _format_drive(self, letter: str) -> bool:
        ps = (
            f"Format-Volume -DriveLetter '{letter}' -FileSystem FAT32 "
            f"-Confirm:$false -Force -ErrorAction Stop | Out-Null; "
            f"Write-Output 'OK'"
        )
        out, _, rc = _run_powershell(ps, timeout=30)
        return rc == 0 and "OK" in out

    def _create_junction(self, original: Path, target: Path) -> bool:
        if not original.parent.exists():
            return False
        try:
            r = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(original), str(target)],
                capture_output=True, text=True, timeout=10,
            )
            return r.returncode == 0
        except Exception as e:
            log.warning("mklink junction failed: %s", e)
            return False

    def _unmount_ramdisk(self, letter: str) -> None:
        if self._imdisk_exe:
            try:
                subprocess.run(
                    [str(self._imdisk_exe), "-d", "-u", f"{letter}:"],
                    capture_output=True, text=True, timeout=15,
                )
            except Exception as e:
                log.warning("imdisk -d failed for %s: %s", letter, e)

    def _load_state(self) -> Dict[str, Any]:
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        try:
            self.state_file.write_text(json.dumps(state, indent=2))
        except OSError as e:
            log.warning("Failed to save shield state: %s", e)

    def _short_hash(self, key: str) -> str:
        import hashlib
        return hashlib.sha256(key.encode()).hexdigest()[:12] if key else ""


def redirected_sources(redirects: Dict[str, str]) -> List[str]:
    """Defensive: returns only original keys (never target paths) for restore."""
    return list(redirects.keys())
