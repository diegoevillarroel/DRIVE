"""
DRIVE — AI SSD Guardian
Flask application factory.
Flask import is deferred to runtime (lazy import).
This avoids breaking tests that only need models/config/path_scanner.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

log = logging.getLogger("drive.app")


def create_app(config=None):
    """
    Create and configure the Flask application.
    Flask is imported lazily to avoid ImportError in test environments.
    """
    from flask import Flask, jsonify, request

    from models import DriveInfo, ScanResult
    from smart_reader import SmartReader
    from path_scanner import PathScanner
    from shield_manager import ShieldManager
    from web_ui import render_ui

    app = Flask(__name__)

    if config is None:
        from config import Config
        config = Config()

    app.config["DRIVE_CONFIG"] = config

    # Initialize components
    smart_reader = SmartReader(config.smartmontools_path)
    path_scanner = PathScanner()
    shield_manager = ShieldManager(data_dir=config.data_dir)

    # Application state
    state = {
        "shield_active": False,
        "last_scan": None,
    }

    # ─── Health ────────────────────────────────────────────────────────

    @app.route("/api/health")
    def health():
        return jsonify({
            "status": "ok",
            "version": "1.0.0",
            "shield_active": state["shield_active"],
        })

    # ─── SSD Scan ─────────────────────────────────────────────────────

    @app.route("/api/scan", methods=["GET"])
    def scan():
        """Run full SSD health + AI impact scan."""
        start = time.time()

        try:
            drive_info = smart_reader.get_drive_info()
        except Exception as e:
            log.error("SMART read failed: %s", e)
            drive_info = DriveInfo(model="Scan failed — run as Administrator")

        frameworks = path_scanner.scan_all()

        total_daily_gb = 0.0
        framework_dicts = []
        for fw in frameworks:
            gb = fw.estimate_daily_writes()
            framework_dicts.append(fw.to_dict())
            total_daily_gb += gb

        if total_daily_gb > 0:
            drive_info.projected_life_months = drive_info.estimate_life_months(total_daily_gb)

        is_shield = shield_manager.is_shield_active()
        state["shield_active"] = is_shield

        result = ScanResult(
            drive=drive_info,
            frameworks=framework_dicts,
            total_daily_gb=round(total_daily_gb, 3),
            shield_active=is_shield,
            scan_duration_ms=int((time.time() - start) * 1000),
        )

        state["last_scan"] = result
        return jsonify(result.to_dict())

    @app.route("/api/drive", methods=["GET"])
    def api_drive():
        try:
            info = smart_reader.get_drive_info()
            return jsonify(info.to_dict())
        except Exception as e:
            log.error("SMART read failed: %s", e)
            return jsonify({"model": "Unavailable", "error": str(e)}), 500

    @app.route("/api/frameworks", methods=["GET"])
    def api_frameworks():
        detected = path_scanner.scan_all()
        return jsonify([fw.to_dict() for fw in detected])

    # ─── Shield ───────────────────────────────────────────────────────

    @app.route("/api/shield/status", methods=["GET"])
    def shield_status():
        is_active = shield_manager.is_shield_active()
        state["shield_active"] = is_active
        return jsonify({
            "active": is_active,
            "ramdisk_letter": shield_manager.get_ramdisk_letter(),
            "redirected_paths": list(shield_manager.get_redirected_paths().keys()),
        })

    @app.route("/api/shield/activate", methods=["POST"])
    def shield_activate():
        data = request.get_json() or {}
        ramdisk_size_gb = data.get("ramdisk_size_gb", 4)

        try:
            result = shield_manager.activate_shield(
                ramdisk_size_gb=ramdisk_size_gb,
                frameworks=state["last_scan"].frameworks if state["last_scan"] else None,
            )
            state["shield_active"] = True
            return jsonify({"success": True, **result})
        except Exception as e:
            log.error("Shield activation failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/shield/deactivate", methods=["POST"])
    def shield_deactivate():
        try:
            result = shield_manager.deactivate_shield()
            state["shield_active"] = False
            return jsonify({"success": True, **result})
        except Exception as e:
            log.error("Shield deactivation failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/shield/benchmark", methods=["POST"])
    def shield_benchmark():
        data = request.get_json() or {}
        duration_sec = data.get("duration_sec", 60)

        try:
            result = shield_manager.run_benchmark(
                duration_sec=duration_sec,
                frameworks=state["last_scan"].frameworks if state["last_scan"] else None,
            )
            return jsonify({"success": True, **result})
        except Exception as e:
            log.error("Benchmark failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    # ─── Web UI ───────────────────────────────────────────────────────

    @app.route("/")
    def index():
        return render_ui()

    return app