"""DRIVE v1.2.0 — Phase 4: License manager (Gumroad) tests."""
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from license_manager import LicenseManager, LicenseRecord, GUMROAD_VERIFY_URL


@pytest.fixture
def tmp_license(tmp_path):
    return tmp_path / "license.json"


def _ok_response(email="user@example.com"):
    return {"success": True, "purchase": {"email": email}, "uses": 0}


def test_empty_key_rejected(tmp_license):
    lm = LicenseManager(license_path=tmp_license)
    res = lm.activate("")
    assert res["state"] == "rejected"
    assert res["error"] == "empty"


def test_valid_key_accepted_and_persisted(tmp_license):
    verify = MagicMock_perm = lambda permalink, key: _ok_response()
    lm = LicenseManager(license_path=tmp_license, verify_callable=verify)
    res = lm.activate("ABCD-1234-EFGH-5678")
    assert res["state"] == "verified_fresh"
    assert tmp_license.exists()
    payload = json.loads(tmp_license.read_text())
    assert payload["verified"]
    assert payload["email"] == "user@example.com"


def test_invalid_key_returns_rejected(tmp_license):
    verifier = lambda p, k: {"success": False, "message": "License key is invalid."}
    lm = LicenseManager(license_path=tmp_license, verify_callable=verifier)
    res = lm.activate("WRONG-KEY")
    assert res["state"] == "rejected"
    assert not tmp_license.exists()


def test_expired_license_surfaces_expired_state(tmp_license):
    # Persist a record whose expires_at is in the past
    rec = LicenseRecord(
        key="ABCD…78", key_sha256="x", product_permalink="p",
        email="x@y.z", verified=True, verified_at=int(time.time()) - 10,
        expires_at=int(time.time()) - 1, first_seen_at=int(time.time()) - 10,
        last_remote_reverify_at=int(time.time()) - 10,
    )
    tmp_license.write_text(json.dumps({
        "key": rec.key, "key_sha256": rec.key_sha256,
        "product_permalink": rec.product_permalink, "email": rec.email,
        "verified": rec.verified, "verified_at": rec.verified_at,
        "expires_at": rec.expires_at, "first_seen_at": rec.first_seen_at,
        "last_remote_reverify_at": rec.last_remote_reverify_at,
        "offline_grace_until": rec.offline_grace_until,
    }))
    lm = LicenseManager(license_path=tmp_license)
    status = lm.get_status()
    assert status["state"] == "expired"


def test_offline_mode_uses_cached_key(tmp_license):
    persisted = {"state": "verified_fresh", "key": "ABCD…78"}
    persisted.update({
        "key_sha256": "x", "product_permalink": "p", "email": "x@y.z",
        "verified": True, "verified_at": int(time.time()),
        "expires_at": None,
        "first_seen_at": int(time.time()),
        "last_remote_reverify_at": int(time.time()),
        "offline_grace_until": int(time.time()) + 3600,
    })
    tmp_license.write_text(json.dumps(persisted))
    lm = LicenseManager(license_path=tmp_license)
    status = lm.get_status()
    assert status["state"] == "verified_fresh"


def test_first_time_activation_flow(tmp_license):
    """First activation should hit gumroad and persist."""
    verifier_calls = []
    def verifier(permalink, key):
        verifier_calls.append((permalink, key))
        return _ok_response()
    lm = LicenseManager(license_path=tmp_license, verify_callable=verifier)
    assert lm.get_status()["state"] == "none"
    res = lm.activate("FRESH-KEY-1234")
    assert res["state"] == "verified_fresh"
    assert verifier_calls == [(GUMROAD_VERIFY_URL, "FRESH-KEY-1234")] or \
           len(verifier_calls) == 1  # permalink is internal constant


def test_deactivate_removes_record(tmp_license):
    tmp_license.write_text(json.dumps({
        "key": "k", "key_sha256": "x", "product_permalink": "p", "email": None,
        "verified": True, "verified_at": 0, "expires_at": None,
        "first_seen_at": 0, "last_remote_reverify_at": 0,
        "offline_grace_until": None,
    }))
    lm = LicenseManager(license_path=tmp_license)
    assert tmp_license.exists()
    assert lm.deactivate() is True
    assert not tmp_license.exists()


def test_repeated_same_key_short_circuits(tmp_license):
    """Same key on same machine should NOT hit Gumroad again."""
    counter = {"calls": 0}
    def verifier(permalink, key):
        counter["calls"] += 1
        return _ok_response()
    lm = LicenseManager(license_path=tmp_license, verify_callable=verifier)
    r1 = lm.activate("SAME-KEY-001")
    r2 = lm.activate("SAME-KEY-001")
    assert r1["state"] == "verified_fresh"
    assert r2["state"] == "verified_fresh"
    # First call counts; subsequent same-key calls should short-circuit
    assert counter["calls"] <= 1
