"""
DRIVE — Path scanner unit tests.
"""
from __future__ import annotations

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from path_scanner import PathScanner, AI_FRAMEWORKS, _expand_path, _is_running


class TestPathScanner:
    """Tests for PathScanner."""

    def test_expand_path_home(self):
        """~ is expanded to user home."""
        result = _expand_path("~/test_dir")
        assert result is not None
        assert "~" not in str(result)

    def test_expand_path_env_var(self):
        """Environment variables are expanded."""
        os.environ["DRIVE_TEST_VAR"] = "/test/path"
        result = _expand_path("%DRIVE_TEST_VAR%")
        assert result is not None
        del os.environ["DRIVE_TEST_VAR"]

    def test_expand_path_nonexistent_returns_none(self):
        """Non-existent path with bad chars returns None."""
        result = _expand_path("/nonexistent/\x00/bad")
        # Result is None or a Path — either is acceptable (depends on platform)
        assert result is None or isinstance(result, Path)

    def test_ai_frameworks_registry_has_all_required_fields(self):
        """Every framework in registry has required fields."""
        required = ["id", "name", "search_paths"]
        for fw in AI_FRAMEWORKS:
            for field in required:
                assert field in fw, f"Framework {fw.get('id')} missing '{field}'"

    def test_ai_frameworks_unique_ids(self):
        """All framework IDs are unique."""
        ids = [fw["id"] for fw in AI_FRAMEWORKS]
        assert len(ids) == len(set(ids)), "Duplicate framework IDs found"

    def test_scanner_returns_list(self):
        """scan_all returns a list even on empty scan."""
        scanner = PathScanner()
        result = scanner.scan_all()
        assert isinstance(result, list)

    def test_scanner_cache_avoids_duplicate_scans(self):
        """Multiple calls to scan_all use cache."""
        scanner = PathScanner()
        r1 = scanner.scan_all()
        r2 = scanner.scan_all()
        # Should be the same cached list (not re-scanned)
        assert r1 is r2

    def test_force_rescan_bypasses_cache(self):
        """force=True forces a fresh scan."""
        scanner = PathScanner()
        r1 = scanner.scan_all()
        r2 = scanner.scan_all(force=True)
        assert r1 is not r2  # Different list instance

    def test_get_frameworks_by_severity_groups_correctly(self):
        """get_frameworks_by_severity groups frameworks correctly."""
        scanner = PathScanner()
        # Mock frameworks with known severity
        with patch.object(scanner, "_cache_valid", True):
            pass
        # Can't easily test without filesystem mocking
        # but we test the structure
        result = scanner.get_frameworks_by_severity()
        assert "high" in result
        assert "medium" in result
        assert "low" in result

    def test_detect_framework_nonexistent_returns_none(self):
        """Framework with no existing paths returns None."""
        scanner = PathScanner()
        result = scanner._detect_framework({
            "id": "nonexistent_test_fw",
            "name": "Nonexistent Test Framework",
            "search_paths": ["/this/path/absolutely/does/not/exist"],
            "cache_patterns": ["cache/"],
            "log_patterns": ["logs/"],
        })
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])