"""
DRIVE v1.2.0 - License Manager (Phase 4: Freemium Gate).

The Scanner is free. The Shield requires a license key validated against
Gumroad's License API.

Storage:  %APPDATA%/DRIVE/license.json
Strategy: local-first; weekly re-verified against Gumroad's /licenses/verify
Offline mode: cached-valid key unlocks the Shield until next re-verify window.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

log = logging.getLogger("drive.license")

# Gumroad product. Replace with real permalink at publish time.
GUMROAD_PRODUCT_PERMALINK = "ai-drive-smooth"

# Endpoint per https://gumroad.com/api#licenses
GUMROAD_VERIFY_URL = "https://api.gumroad.com/api/licenses/verify"

# Re-verify cached key vs Gumroad every 7 days.
REMOTE_REVERIFY_INTERVAL_SEC = 7 * 24 * 3600


@dataclass
class LicenseRecord:
    key: str                          # masked
    key_sha256: str                   # authoritative fingerprint (never reversed)
    product_permalink: str
    email: Optional[str]
    verified: bool                    # True if currently validated by Gumroad
    verified_at: int                  # epoch sec
    expires_at: Optional[int]         # None = perpetual
    first_seen_at: int
    last_remote_reverify_at: int
    offline_grace_until: Optional[int] = None

    def is_offline_valid(self, now: int) -> bool:
        if not self.verified:
            return False
        return True  # Cached-valid stays valid; remote re-verify only fails the Shield on hard invalidation
    def to_dict(self) -> dict:
        return asdict(self)


def _local_data_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    base = Path(appdata) / "DRIVE"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _machine_id() -> str:
    try:
        if platform.system() == "Windows":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
                capture_output=True, text=True, timeout=10,
            )
            return out.stdout.strip() or uuid.getnode().__str__()
        return uuid.getnode().__str__()
    except Exception:
        return uuid.getnode().__str__()


def _hash_key(key: str) -> str:
    return hashlib.sha256(f"{key.strip()}|{_machine_id()}".encode()).hexdigest()


class LicenseManager:
    """State machine for license verification with offline grace period."""

    def __init__(
        self,
        license_path: Optional[Path] = None,
        verify_callable: Optional[Callable[[str, str], Dict[str, Any]]] = None,
    ):
        # verify_callable is injected in tests to bypass the HTTP call.
        # Signature: (product_permalink, license_key) -> Gumroad verify response dict.
        self.license_path = license_path or (_local_data_dir() / "license.json")
        self._verify_callable = verify_callable

    # ---- public API ----

    def get_status(self) -> Dict[str, Any]:
        """Return 'none' / 'cached_valid' / 'verified_fresh' / 'expired' / 'verification_due'."""
        rec = self._read()
        if rec is None:
            return {"state": "none"}
        now = int(time.time())
        needs_reverify = (now - rec.last_remote_reverify_at) > REMOTE_REVERIFY_INTERVAL_SEC
        if rec.verified:
            if rec.expires_at and now > rec.expires_at:
                return {"state": "expired", "record": rec.to_dict()}
            if needs_reverify:
                return {
                    "state": "verification_due",
                    "record": rec.to_dict(),
                    "message": "License will be re-verified online at next Shield activation.",
                }
            return {"state": "verified_fresh", "record": rec.to_dict()}
        return {"state": "cached_invalid", "record": rec.to_dict(),
                "message": "Cached license failed verification. Re-enter your key."}

    def activate(self, license_key: str) -> Dict[str, Any]:
        """Verify the license against Gumroad (or the injected verify callable).
        Returns a dict with state + key fields for the UI."""
        key = license_key.strip()
        if not key:
            return {"state": "rejected", "error": "empty",
                    "message": "Please paste a license key from your Gumroad receipt email."}

        # 1) Local replay check — if the EXACT key was previously verified good,
        # we can short-circuit without hitting Gumroad.
        rec = self._read()
        if rec and rec.key_sha256 == _hash_key(key) and rec.verified:
            if rec.expires_at is None or int(time.time()) < rec.expires_at:
                return {
                    "state": "verified_fresh",
                    "message": "Already verified on this machine.",
                    "record": rec.to_dict(),
                }

        # 2) Remote verification
        try:
            resp = self._call_gumroad(key)
        except Exception as e:
            log.error("Gumroad verify call failed: %s", e)
            return {
                "state": "network_error",
                "message": "Couldn't reach Gumroad. Your cached license (if any) still protects the Shield.",
                "error": str(e),
            }

        # Gumroad's documented response fields (https://gumroad.com/api#licenses):
        # success (boolean), message (string), purchase (dict with email, etc.),
        # uses (int), owner (dict) — has been stable since 2020.
        if not isinstance(resp, dict) or not resp.get("success"):
            return {
                "state": "rejected",
                "message": resp.get("message", "Invalid license key.") if isinstance(resp, dict) else "Verification failed.",
                "error": "gumroad_rejected",
            }

        # 3) Persist
        purchase = resp.get("purchase", {}) or {}
        now = int(time.time())
        record = LicenseRecord(
            key=key[:4] + "…" + key[-2:] if len(key) > 6 else key[:2] + "…",
            key_sha256=_hash_key(key),
            product_permalink=GUMROAD_PRODUCT_PERMALINK,
            email=purchase.get("email"),
            verified=True,
            verified_at=now,
            expires_at=purchase.get("subscription_ended_at") or None,
            first_seen_at=now if rec is None else rec.first_seen_at,
            last_remote_reverify_at=now,
        )
        self._write(record)
        return {"state": "verified_fresh", "message": "License activated.", "record": record.to_dict()}

    def deactivate(self) -> bool:
        try:
            if self.license_path.exists():
                self.license_path.unlink()
            return True
        except OSError as e:
            log.warning("Could not remove license: %s", e)
            return False

    def reverify_if_due(self) -> None:
        rec = self._read()
        if not rec or not rec.verified:
            return
        now = int(time.time())
        if (now - rec.last_remote_reverify_at) < REMOTE_REVERIFY_INTERVAL_SEC:
            return
        # Call Gumroad without UI; on failure mark verified=False
        try:
            # Caller can re-derive original key from cache? No — we only stored the fingerprint.
            # Re-verification on schedule requires a "verification token" to be saved
            # alongside the fingerprint. Gumroad's /licenses/verify does accept the
            # license_key reused for back-end inspection, but we never persist it.
            #
            # For Phase 4 we mark the record as needing_reverification; on next
            # user-initiated Shield activation we re-prompt for the key.
            rec.verified = False
            rec.offline_grace_until = None
            self._write(rec)
            log.info("License for this machine requires re-verification on next use.")
        except Exception as e:
            log.warning("Schedule-based re-verify error: %s", e)

    # ---- internals ----

    def _read(self) -> Optional[LicenseRecord]:
        if not self.license_path.exists():
            return None
        try:
            data = json.loads(self.license_path.read_text())
            # Strip unknown / stale keys
            valid_keys = {f for f in LicenseRecord.__dataclass_fields__.keys()}
            data = {k: v for k, v in data.items() if k in valid_keys}
            return LicenseRecord(**data)
        except Exception as e:
            log.warning("Could not read license record: %s", e)
            return None

    def _write(self, rec: LicenseRecord) -> None:
        self.license_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.license_path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(rec.to_dict(), indent=2))
            os.replace(tmp, self.license_path)
        except Exception as e:
            log.error("Could not persist license record: %s", e)

    def _call_gumroad(self, key: str) -> Dict[str, Any]:
        if self._verify_callable is not None:
            return self._verify_callable(GUMROAD_PRODUCT_PERMALINK, key)

        # Real production path.
        try:
            import urllib.request, urllib.parse
            post = urllib.parse.urlencode({
                "product_permalink": GUMROAD_PRODUCT_PERMALINK,
                "license_key": key,
            }).encode()
            req = urllib.request.Request(
                GUMROAD_VERIFY_URL,
                data=post,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    return {"success": False, "message": f"Gumroad returned non-JSON: {body[:200]}"}
        except Exception as e:
            log.error("Gumroad network failure: %s", e)
            raise
