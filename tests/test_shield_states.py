"""DRIVE v1.2.0 - Phase 1: Shield state machine truthfulness."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from shield_manager import ShieldManager, _is_admin


def _make(tmp_path, *, imdisk_exe, imdisk_installer=None):
    """ShieldManager with imdisk paths stubbed before the constructor does its disk lookup."""
    sm = ShieldManager.__new__(ShieldManager)
    sm.data_dir = tmp_path
    sm.data_dir.mkdir(parents=True, exist_ok=True)
    sm.state_file = tmp_path / "shield_state.json"
    sm._imdisk_exe = imdisk_exe
    sm._imdisk_installer = imdisk_installer
    return sm


# ----- 1) NOT ATTEMPTED -----

def test_not_attempted_when_no_state_file(tmp_path):
    sm = _make(tmp_path, imdisk_exe=Path("/fake/imdisk.exe"))
    with patch("shield_manager._is_admin", return_value=True):
        s = sm.get_status()
    assert s.state == "not_attempted"
    assert not s.active


# ----- 2) ImDisk missing -----

def test_imdisk_missing_returns_clear_error(tmp_path):
    sm = _make(tmp_path, imdisk_exe=None, imdisk_installer=None)
    with patch("shield_manager._is_admin", return_value=True):
        s = sm.get_status()
    assert s.state == "needs_imdisk"
    assert not s.active
    assert s.error_code == "imdisk_missing"
    assert "ImDisk" in s.error_message


# ----- 3) Admin missing -----

def test_not_admin_returns_setup_state(tmp_path):
    sm = _make(tmp_path, imdisk_exe=Path("/fake/imdisk.exe"))
    with patch("shield_manager._is_admin", return_value=False):
        s = sm.get_status()
    assert s.state == "needs_admin_setup"
    assert s.error_code == "not_admin"


# ----- 4) Truly active only when verified -----

def test_active_only_when_mount_verified_and_junctions_exist_case_b(tmp_path):
    """Case B specifically: mount ok, junctions GONE."""
    sm = _make(tmp_path, imdisk_exe=Path("/fake/imdisk.exe"))
    state = {
        "active": True,
        "activated_at": "2026-06-23T00:00:00Z",
        "ramdisk_letter": "Z",
        "ramdisk_size_gb": 4,
        "redirects": {
            str(tmp_path / "app1"): str(tmp_path / "rd" / "app1"),
            str(tmp_path / "app2"): str(tmp_path / "rd" / "app2"),
        },
        "est_savings_gb": 0.0,
    }
    sm.state_file.write_text(json.dumps(state))
    with patch("shield_manager._is_admin", return_value=True), \
         patch("shield_manager._ramdisk_already_mounted", return_value=3.5), \
         patch("shield_manager._junction_exists", return_value=False):
        s = sm.get_status()
    assert s.state == "redirects_failed"
    assert not s.active
    assert "redirect" in s.error_message.lower() or "junction" in s.error_message.lower()


def test_active_state_when_everything_verified(tmp_path):
    sm = _make(tmp_path, imdisk_exe=Path("/fake/imdisk.exe"))
    # Pre-create the original dirs so Path.exists() returns True in the verifier
    (tmp_path / "app1").mkdir(exist_ok=True)
    (tmp_path / "app2").mkdir(exist_ok=True)
    state = {
        "active": True,
        "activated_at": "2026-06-23T00:00:00Z",
        "ramdisk_letter": "Z",
        "ramdisk_size_gb": 4,
        "redirects": {
            str(tmp_path / "app1"): str(tmp_path / "rd" / "app1"),
            str(tmp_path / "app2"): str(tmp_path / "rd" / "app2"),
        },
        "est_savings_gb": 0.0,
    }
    sm.state_file.write_text(json.dumps(state))
    with patch("shield_manager._is_admin", return_value=True), \
         patch("shield_manager._ramdisk_already_mounted", return_value=3.5), \
         patch("shield_manager._junction_exists", return_value=True):
        s = sm.get_status()
    assert s.state == "active"
    assert s.active is True
    assert s.verified_via_os is True
    assert s.ramdisk_free_gb == 3.5
    assert s.redirected_count == 2

def test_activate_blocks_without_license(tmp_path):
    sm = _make(tmp_path, imdisk_exe=Path("/fake/imdisk.exe"))
    s = sm.activate_shield(license_verified=False)
    assert s.state == "needs_license"
    assert s.error_code == "no_license"


def test_activate_blocks_without_admin(tmp_path):
    sm = _make(tmp_path, imdisk_exe=Path("/fake/imdisk.exe"))
    with patch("shield_manager._is_admin", return_value=False):
        s = sm.activate_shield(license_verified=True)
    assert s.state == "needs_admin_setup"


def test_activate_blocks_when_mount_unverified(tmp_path):
    """The audit's worst case: imdisk says success but the mount is not visible."""
    sm = _make(tmp_path, imdisk_exe=Path("/fake/imdisk.exe"))
    with patch("shield_manager._is_admin", return_value=True), \
         patch.object(ShieldManager, "_choose_drive_letter", return_value="Z"), \
         patch.object(ShieldManager, "_create_junction", return_value=True), \
         patch("shield_manager._ramdisk_already_mounted", return_value=None), \
         patch("subprocess.run", return_value=MagicMock(returncode=0, stderr="")):
        s = sm.activate_shield(license_verified=True)
    assert s.state != "active"
    assert s.state == "driver_load_failed"
    assert s.error_code == "mount_unverified"


def test_deactivate_no_state_graceful(tmp_path):
    sm = _make(tmp_path, imdisk_exe=Path("/fake/imdisk.exe"))
    out = sm.deactivate_shield()
    assert out["success"] is True
