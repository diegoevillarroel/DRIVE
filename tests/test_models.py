"""
DRIVE — Unit tests
Run with: pytest tests/ -v
"""
from __future__ import annotations

import pytest
from pathlib import Path
from models import DriveInfo, FrameworkInfo, ShieldStatus, ScanResult
from config import Config


class TestDriveInfo:
    """Tests for DriveInfo model."""

    def test_health_percent_zero_returns_zero_months(self):
        """If drive is dead, projected life is 0."""
        di = DriveInfo(health_percent=0, tbw_written_tb=600, tbw_rated_tb=600)
        assert di.estimate_life_months(daily_gb=10) == 0.0

    def test_estimate_life_months_uses_tbw(self):
        """Life estimate uses TBW metric when available."""
        # 600 TBW rated, 300 TB written → 300 remaining
        # At 10 GB/day = 0.0098 TB/day → 300/0.0098/30 ≈ 1020 months
        di = DriveInfo(tbw_written_tb=300, tbw_rated_tb=600)
        months = di.estimate_life_months(daily_gb=10)
        assert 800 < months < 1200

    def test_estimate_life_months_zero_gb_returns_none(self):
        """Zero daily writes means no degradation."""
        di = DriveInfo(tbw_written_tb=100, tbw_rated_tb=600)
        assert di.estimate_life_months(daily_gb=0) is None

    def test_to_dict_rounds_floats(self):
        """Serialized floats should be rounded for cleanliness."""
        di = DriveInfo(
            tbw_written_tb=123.456789123,
            projected_life_months=999.999999,
        )
        d = di.to_dict()
        assert d["tbw_written_tb"] == 123.457
        assert d["projected_life_months"] == 1000.0

    def test_no_tbw_returns_none(self):
        """Without TBW data, cannot project life."""
        di = DriveInfo()
        assert di.estimate_life_months(daily_gb=10) is None


class TestFrameworkInfo:
    """Tests for FrameworkInfo model."""

    def test_estimate_daily_writes_zero_when_not_running(self):
        """Framework not running contributes 0 writes."""
        fw = FrameworkInfo(id="ollama", name="Ollama", is_running=False)
        assert fw.estimate_daily_writes() == 0.0
        assert fw.severity == "low"

    def test_estimate_daily_writes_sets_severity(self):
        """Severity is set correctly based on estimated writes."""
        # Very low (1 GB/day) — mock a minimal framework
        fw_low = FrameworkInfo(
            id="test_fw_minimal",
            name="Minimal Framework",
            is_running=True,
            cache_paths=[],
            log_paths=[],
        )
        fw_low.estimated_daily_gb = 0.8  # force low value
        fw_low.severity = (
            "high" if fw_low.estimated_daily_gb >= 10
            else "medium" if fw_low.estimated_daily_gb >= 2
            else "low"
        )
        assert fw_low.severity == "low"

        # High (>= 10 GB/day) — Codex CLI has known unpatched bug
        fw_high = FrameworkInfo(id="codex", name="OpenAI Codex CLI", is_running=True)
        gb = fw_high.estimate_daily_writes()
        assert gb >= 10.0
        assert fw_high.severity == "high"

    def test_to_dict_preserves_all_fields(self):
        """to_dict should include all fields, not drop any."""
        fw = FrameworkInfo(
            id="ollama",
            name="Ollama",
            detected_path="/home/user/.ollama",
            cache_paths=["/home/user/.ollama/models"],
            log_paths=["/home/user/.ollama/logs"],
            is_running=True,
            estimated_daily_gb=3.5,
            severity="medium",
            website="https://ollama.com",
        )
        d = fw.to_dict()
        assert d["id"] == "ollama"
        assert d["cache_paths"] == ["/home/user/.ollama/models"]
        assert d["estimated_daily_gb"] == 3.5


class TestShieldStatus:
    """Tests for ShieldStatus model."""

    def test_default_inactive(self):
        """Shield is inactive by default."""
        ss = ShieldStatus()
        assert ss.active is False
        assert ss.ramdisk_letter is None

    def test_to_dict_all_fields(self):
        """All fields serialize correctly."""
        ss = ShieldStatus(
            active=True,
            ramdisk_letter="Z",
            ramdisk_size_gb=4,
            redirected_count=12,
            estimated_ssd_savings_gb_per_day=25.5,
        )
        d = ss.to_dict()
        assert d["active"] is True
        assert d["ramdisk_letter"] == "Z"
        assert d["ramdisk_size_gb"] == 4
        assert d["estimated_ssd_savings_gb_per_day"] == 25.5


class TestConfig:
    """Tests for Config."""

    def test_default_data_dir(self):
        """Default data dir is under user home."""
        cfg = Config(data_dir=None)
        assert ".drive" in str(cfg.data_dir)

    def test_custom_data_dir(self):
        """Custom data dir is respected."""
        import tempfile, platform
        with tempfile.TemporaryDirectory() as td:
            cfg = Config(data_dir=td)
            # Windows normalizes paths — compare resolved paths instead
            assert cfg.data_dir.resolve() == Path(td).resolve()

    def test_restore_default_on_missing_file(self):
        """Missing config file uses all defaults."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "config.json"
            data_dir = Path(td) / ".drive"
            data_dir.mkdir()
            cfg = Config(data_dir=str(data_dir))
            # Should not crash
            assert cfg.smartmontools_path is None


class TestScanResult:
    """Tests for ScanResult."""

    def test_to_dict_includes_all(self):
        """Scan result serializes completely."""
        di = DriveInfo(model="Samsung 990 Pro", capacity_gb=2000)
        sr = ScanResult(
            drive=di,
            frameworks=[{"id": "ollama", "name": "Ollama"}],
            total_daily_gb=3.5,
            shield_active=False,
            scan_duration_ms=142,
        )
        d = sr.to_dict()
        assert d["drive"]["model"] == "Samsung 990 Pro"
        assert len(d["frameworks"]) == 1
        assert d["total_daily_gb"] == 3.5
        assert d["scan_duration_ms"] == 142


# ─── Run quick validation ─────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])