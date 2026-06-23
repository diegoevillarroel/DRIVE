"""
DRIVE v1.2.0 — AI SSD Guardian
Flask application factory + web routes + embedded UI.

Phase 1 fixes:
  - process_inspector replaces PathScanner for real process detection
  - Background thread for framework sampling (no more blocking /api/scan)
  - Shield status driven by ShieldManager.get_status() (honest, OS-verified)
  - License endpoints wired for Gumroad
  - Admin elevation endpoint
  - Share panel endpoints
"""
from __future__ import annotations

import logging
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request, Response

# Import the HONEST ShieldStatus from shield_manager (not the stub in models.py)
from shield_manager import ShieldManager, ShieldStatus as ShieldStatusReal
from smart_reader import SmartReader
from process_inspector import (
    detect_ai_processes,
    measure_framework_disk_usage,
    sample_framework_writes,
    sample_disk_writes,
    DiskSample,
)
from estimate_registry import estimate_for, confidence_for
from license_manager import LicenseManager
from share_panel import build_share_report, build_share_card_svg, build_share_card_png
from config import Config
from models import DriveInfo, ScanResult, AppState

log = logging.getLogger("drive.app")


# ─── Background Framework Sampler ────────────────────────────────────────────
# Avoids blocking /api/scan with time.sleep() + rglob.
# Runs sampling in a daemon thread; last result cached in memory.

class BackgroundSampler:
    """Periodically samples framework write rates in a background thread."""

    def __init__(self, interval_sec: float = 30.0, sample_seconds: float = 5.0):
        self.interval_sec = interval_sec
        self.sample_seconds = sample_seconds
        self._last_result: Dict[str, Any] = {}
        self._last_time: float = 0.0
        self._lock = threading.Lock()
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        log.info("BackgroundSampler started (interval=%ss, sample=%ss)",
                 self.interval_sec, self.sample_seconds)

    def _loop(self) -> None:
        while self._running:
            try:
                result = sample_framework_writes(seconds=self.sample_seconds)
                with self._lock:
                    self._last_result = result
                    self._last_time = time.time()
            except Exception as e:
                log.error("BackgroundSampler error: %s", e)
            time.sleep(self.interval_sec)

    def get_latest(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._last_result)

    def stop(self) -> None:
        self._running = False


def create_app(config: Optional[Config] = None) -> Flask:
    app = Flask(__name__)

    if config is None:
        config = Config()

    app.config["DRIVE_CONFIG"] = config

    # ─── Initialize components ──────────────────────────────────────
    smart_reader = SmartReader(config.smartmontools_path)
    shield_manager = ShieldManager()
    license_manager = LicenseManager()

    # Background sampler for non-blocking framework write rates
    sampler = BackgroundSampler(interval_sec=30.0, sample_seconds=5.0)
    sampler.start()

    # In-memory state
    state: AppState = {
        "shield_active": shield_manager.get_status().active,
        "last_scan": None,
        "last_scan_time": None,
        "ramdisk_letter": shield_manager.get_status().ramdisk_letter,
    }

    # ─── API Routes ──────────────────────────────────────────────────

    @app.route("/api/health")
    def health():
        return jsonify({
            "status": "ok",
            "version": "1.2.0",
            "platform": platform.system(),
        })

    @app.route("/api/scan", methods=["GET"])
    def scan():
        """Run full SSD + AI impact scan. Non-blocking via cached background samples."""
        start = time.time()
        sample_seconds = float(request.args.get("sample_seconds", 0))

        # 1. Read SMART data (quick, subprocess to smartctl)
        drive_info = smart_reader.get_drive_info()

        # 2. Detect running AI processes (PowerShell, ~5s max)
        detected_procs = detect_ai_processes(timeout_sec=10)

        # 3. Measure on-disk framework usage (fast — no rglob on huge dirs)
                disk_usage = measure_framework_disk_usage()

                # 4. Get background-sampled write rates (non-blocking)
                bg_writes = sampler.get_latest()

                # If caller asked for a live sample, run it in a thread (cap 2s to stay responsive)
                live_writes: Dict[str, float] = {}
                if sample_seconds > 0:
                    sample_seconds = min(sample_seconds, 2.0)
                    result_holder: list = [{}]

                    def _bg_sample():
                        try:
                            result_holder[0] = sample_framework_writes(seconds=sample_seconds)
                        except Exception as e:
                            log.warning("Live sample failed (non-fatal): %s", e)

                    t = threading.Thread(target=_bg_sample)
                    t.start()
                    t.join(timeout=sample_seconds + 2)
                    live_writes = result_holder[0]

        # 5. Build framework info list — merge detected processes + estimates
        framework_infos = []
        seen_ids = set()
        total_daily_gb = 0.0

        for proc in detected_procs:
            tool_id = proc.name.lower().replace(" ", "_").replace("(", "").replace(")", "")
            # Normalize common names to registry keys
            id_map = {
                "ollama_server": "ollama",
                "ollama": "ollama",
                "claude_code_(anthropic)": "claude_code",
                "claude_code": "claude_code",
                "openai_codex_cli": "codex",
                "cursor_ai": "cursor",
                "lm_studio": "lm_studio",
                "jan_(cerebras)": "jan",
                "chromadb": "chroma",
                "n8n_workflow": "n8n",
                "crewai_agent": "crewai",
                "autogen_(microsoft)": "autogen",
                "autogpt": "autogpt",
                "hermes_agent_(nous)": "hermes",
            }
            reg_id = id_map.get(tool_id, tool_id)
            est = estimate_for(reg_id)
            confidence = confidence_for(reg_id)

            # Use live-measured rate if available, else background, else estimate
            measured_rate = live_writes.get(proc.label) or bg_writes.get(proc.label)
            if measured_rate and measured_rate > 0:
                daily_gb = round(measured_rate * 86400 / (1024**3), 2)
                source = "live_sample"
                confidence = "measured"
            else:
                daily_gb = est["gb_per_day"]
                source = est["source"]

            severity = "high" if daily_gb >= 10 else "medium" if daily_gb >= 2 else "low"

            fw_info = {
                "id": reg_id,
                "name": proc.label,
                "pid": proc.pid,
                "estimated_daily_gb": daily_gb,
                "severity": severity,
                "confidence": confidence,
                "source": source,
                "measured_bytes_per_sec": measured_rate if measured_rate else None,
                "on_disk_size_bytes": proc.on_disk_size_bytes,
            }
            key = (reg_id, proc.label)
            if key not in seen_ids:
                seen_ids.add(key)
                framework_infos.append(fw_info)
                total_daily_gb += daily_gb

        # 6. Also add frameworks from disk_usage that weren't detected as running
        for label, size_bytes in disk_usage.items():
            if any(label in f["name"] for f in framework_infos):
                continue
            # Normalize label to registry key
            label_map = {
                "Ollama models": "ollama",
                "Claude Code projects": "claude_code",
                "Cursor storage": "cursor",
                "n8n logs & DB": "n8n",
                "ChromaDB persist": "chroma",
                "Hermes Agent": "hermes",
                "LM Studio cache": "lm_studio",
            }
            reg_id = label_map.get(label, label.lower().replace(" ", "_"))
            est = estimate_for(reg_id)
            confidence = confidence_for(reg_id)
            daily_gb = est["gb_per_day"]
            severity = "high" if daily_gb >= 10 else "medium" if daily_gb >= 2 else "low"

            fw_info = {
                "id": reg_id,
                "name": label,
                "pid": 0,
                "estimated_daily_gb": daily_gb,
                "severity": severity,
                "confidence": confidence,
                "source": est["source"],
                "measured_bytes_per_sec": None,
                "on_disk_size_bytes": size_bytes,
            }
            framework_infos.append(fw_info)
            total_daily_gb += daily_gb

        # 7. Calculate projected drive life
        if drive_info.tbw_written_tb and total_daily_gb > 0:
            drive_info.projected_life_months = drive_info.estimate_life_months(total_daily_gb)

        scan_result = ScanResult(
            drive=drive_info,
            frameworks=framework_infos,
            total_daily_gb=total_daily_gb,
            shield_active=shield_manager.get_status().active,
            scan_duration_ms=int((time.time() - start) * 1000),
        )

        state["last_scan"] = scan_result
        state["last_scan_time"] = time.time()

        return jsonify(scan_result.to_dict())

    @app.route("/api/drive", methods=["GET"])
    def drive_info():
        """Get SSD health info only."""
        info = smart_reader.get_drive_info()
        return jsonify(info.to_dict())

    @app.route("/api/frameworks", methods=["GET"])
    def frameworks():
        """Detect active AI frameworks only."""
        procs = detect_ai_processes(timeout_sec=10)
        return jsonify([p.to_dict() for p in procs])

    # ─── Shield Routes (honest, OS-verified) ───────────────────────

    @app.route("/api/shield/status", methods=["GET"])
    def shield_status():
        """Get current shield status — ALWAYS re-verified against OS."""
        status = shield_manager.get_status()
        state["shield_active"] = status.active
        return jsonify(status.to_dict())

    @app.route("/api/shield/activate", methods=["POST"])
    def shield_activate():
        """Activate SSD protection shield. Requires license."""
        data = request.get_json() or {}
        ramdisk_size_gb = data.get("ramdisk_size_gb", 4)
        license_key = data.get("license_key")

        # Verify license
        license_verified = False
        if license_key:
            lr = license_manager.activate(license_key)
            if lr.get("state") in ("verified_fresh", "cached_valid"):
                license_verified = True
        else:
            lic_status = license_manager.get_status()
            if lic_status.get("state") in ("verified_fresh", "verification_due"):
                license_verified = True

        if not license_verified:
            return jsonify({
                "success": False,
                "error": "License required",
                "state": "needs_license",
            }), 403

        result = shield_manager.activate_shield(
            ramdisk_size_gb=ramdisk_size_gb,
            frameworks=state["last_scan"].frameworks if state["last_scan"] else None,
            license_key=license_key,
            license_verified=True,
        )
        state["shield_active"] = result.active
        state["ramdisk_letter"] = result.ramdisk_letter
        return jsonify({"success": result.active, **result.to_dict()})

    @app.route("/api/shield/deactivate", methods=["POST"])
    def shield_deactivate():
        """Deactivate shield and restore original paths."""
        result = shield_manager.deactivate_shield()
        state["shield_active"] = False
        return jsonify(result)

    @app.route("/api/shield/benchmark", methods=["POST"])
    def shield_benchmark():
        """Run write benchmark."""
        data = request.get_json() or {}
        duration_sec = data.get("duration_sec", 10)
        result = shield_manager.run_benchmark(duration_sec=duration_sec)
        return jsonify(result)

    # ─── License Routes ─────────────────────────────────────────────

    @app.route("/api/license/status", methods=["GET"])
    def license_status():
        """Get current license status."""
        return jsonify(license_manager.get_status())

    @app.route("/api/license/activate", methods=["POST"])
    def license_activate():
        """Activate a license key."""
        data = request.get_json() or {}
        key = data.get("license_key", "").strip()
        if not key:
            return jsonify({"state": "rejected", "error": "empty",
                           "message": "Paste your license key."}), 400
        result = license_manager.activate(key)
        return jsonify(result)

    @app.route("/api/license/deactivate", methods=["POST"])
    def license_deactivate():
        """Remove stored license."""
        ok = license_manager.deactivate()
        return jsonify({"success": ok})

    # ─── Admin Elevation ────────────────────────────────────────────

    @app.route("/api/admin/elevate", methods=["POST"])
    def admin_elevate():
        """Re-launch DRIVE with UAC admin elevation."""
        pid = shield_manager.request_elevation_and_restart()
        if pid > 0:
            return jsonify({"success": True, "message": "Elevating. New instance will start with admin."})
        return jsonify({"success": False, "error": "Elevation failed or cancelled by user."}), 500

    # ─── Share Routes ──────────────────────────────────────────────

    @app.route("/api/share/text", methods=["GET"])
    def share_text():
        """Get compact text report for sharing."""
        scan = state["last_scan"]
        if scan is None:
            return jsonify({"text": "Run a scan first."})
        shield = shield_manager.get_status()
        text = build_share_report(scan.to_dict(), shield)
        return jsonify({"text": text})

    @app.route("/api/share/card.svg", methods=["GET"])
    def share_card_svg():
        """SVG share card."""
        scan = state["last_scan"]
        if scan is None:
            return Response("<svg></svg>", mimetype="image/svg+xml")
        shield = shield_manager.get_status()
        svg = build_share_card_svg(scan.to_dict(), shield)
        return Response(svg, mimetype="image/svg+xml")

    @app.route("/api/share/card.png", methods=["GET"])
    def share_card_png():
        """PNG share card (1200x630)."""
        scan = state["last_scan"]
        if scan is None:
            return Response(b"", mimetype="image/png")
        shield = shield_manager.get_status()
        png_bytes = build_share_card_png(scan.to_dict(), shield)
        return Response(png_bytes, mimetype="image/png")

    # ─── Config Route ──────────────────────────────────────────────

    @app.route("/api/config", methods=["GET"])
    def get_config():
        return jsonify({
            "smartmontools_path": config.smartmontools_path,
            "data_dir": str(config.data_dir),
            "version": "1.2.0",
        })

    # ─── Web UI ────────────────────────────────────────────────────

    @app.route("/")
    def index():
        return render_ui()

    return app


# ─── Embedded Web UI ──────────────────────────────────────────────────────────
from v2_ui import render_ui
