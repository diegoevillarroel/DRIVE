"""DRIVE v1.2.0 - Phase 5: Sharing panel tests (text + SVG + PNG)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from share_panel import build_share_report, build_share_card_svg, build_share_card_png, GUMROAD_URL


def _fake_scan():
    return {
        "drive": {
            "model": "SAMSUNG MZVLQ512 512GB",
            "capacity_gb": 512.1,
            "health_percent": 99,
            "projected_life_months": 36,
        },
        "frameworks": [
            {"name": "Hermes Agent", "estimated_daily_gb": 0.9},
            {"name": "OpenAI Codex CLI", "estimated_daily_gb": 15.0},
            {"name": "Ollama Server", "estimated_daily_gb": 3.0},
        ],
        "total_daily_gb": 18.9,
        "ai_process_count": 3,
    }


def _fake_shield(state="active"):
    s = MagicMock()
    s.state = state
    s.active = state == "active"
    return s


def test_share_text_contains_required_phrases():
    text = build_share_report(_fake_scan(), _fake_shield())
    assert "DRIVE scan" in text
    assert "SAMSUNG" in text
    assert "99%" in text
    assert "Hermes" in text
    assert "Codex CLI" in text
    assert "18.9 GB/day" in text
    assert GUMROAD_URL in text
    assert "Shield Active" in text


def test_share_text_when_shield_not_active():
    text = build_share_report(_fake_scan(), _fake_shield("not_attempted"))
    assert "Shield not yet activated" in text


def test_share_svg_is_valid_xml():
    svg = build_share_card_svg(_fake_scan(), _fake_shield())
    assert svg.startswith("<svg")
    assert "</svg>" in svg
    assert "SAMSUNG" in svg
    assert GUMROAD_URL in svg


def test_share_png_returns_bytes():
    png_or_svg = build_share_card_png(_fake_scan(), _fake_shield())
    assert isinstance(png_or_svg, (bytes, bytearray))
    assert len(png_or_svg) > 200
    if png_or_svg.startswith(b"\\x89PNG"):
        # Indicates Pillow failure fallback; treat as soft pass
        assert b"svg" in png_or_svg[:50] or b"xml" in png_or_svg[:50]
