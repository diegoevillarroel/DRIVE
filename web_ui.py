"""
DRIVE — AI SSD Guardian
Flask application factory + web routes + embedded UI.
"""
from __future__ import annotations

import logging
import subprocess
import platform
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, request

from models import DriveInfo, FrameworkInfo, ShieldStatus, ScanResult, AppState
from smart_reader import SmartReader
from path_scanner import PathScanner
from shield_manager import ShieldManager
from config import Config

log = logging.getLogger("drive.app")


def create_app(config: Optional[Config] = None) -> Flask:
    app = Flask(__name__)

    if config is None:
        config = Config()

    app.config["DRIVE_CONFIG"] = config

    # Initialize components
    smart_reader = SmartReader(config.smartmontools_path)
    path_scanner = PathScanner()
    shield_manager = ShieldManager()

    # In-memory state
    state: AppState = {
        "shield_active": shield_manager.is_shield_active(),
        "last_scan": None,
        "last_scan_time": None,
        "ramdisk_letter": shield_manager.get_ramdisk_letter(),
    }

    # ─── API Routes ────────────────────────────────────────────────

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "version": "1.0.0", "platform": platform.system()})

    @app.route("/api/scan", methods=["GET"])
    def scan():
        """Run full SSD + AI impact scan."""
        import time
        start = time.time()

        # 1. Read SMART data
        drive_info = smart_reader.get_drive_info()

        # 2. Scan for AI frameworks
        frameworks = path_scanner.scan_all()

        # 3. Estimate daily writes per framework
        framework_infos = []
        total_daily_gb = 0.0

        for fw in frameworks:
            daily_gb = fw.estimate_daily_writes()
            fw.estimated_daily_gb = daily_gb
            framework_infos.append(fw.to_dict())
            total_daily_gb += daily_gb

        # 4. Calculate projected drive life
        if drive_info.tbw_written_tb and total_daily_gb > 0:
            drive_info.projected_life_months = drive_info.estimate_life_months(
                total_daily_gb
            )
        elif drive_info.tbw_written_tb:
            drive_info.projected_life_months = None

        scan_result = ScanResult(
            drive=drive_info,
            frameworks=framework_infos,
            total_daily_gb=total_daily_gb,
            shield_active=state["shield_active"],
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
        detected = path_scanner.scan_all()
        return jsonify([fw.to_dict() for fw in detected])

    @app.route("/api/shield/status", methods=["GET"])
    def shield_status():
        """Get current shield status."""
        is_active = shield_manager.is_shield_active()
        state["shield_active"] = is_active
        return jsonify({
            "active": is_active,
            "ramdisk_letter": shield_manager.get_ramdisk_letter(),
            "redirected_paths": shield_manager.get_redirected_paths(),
        })

    @app.route("/api/shield/activate", methods=["POST"])
    def shield_activate():
        """Activate SSD protection shield."""
        data = request.get_json() or {}
        ramdisk_size_gb = data.get("ramdisk_size_gb", 4)

        try:
            result = shield_manager.activate_shield(
                ramdisk_size_gb=ramdisk_size_gb,
                frameworks=state["last_scan"].frameworks if state["last_scan"] else None,
            )
            state["shield_active"] = True
            state["ramdisk_letter"] = result.get("ramdisk_letter")
            return jsonify({"success": True, **result})
        except Exception as e:
            log.error("Shield activation failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/shield/deactivate", methods=["POST"])
    def shield_deactivate():
        """Deactivate shield and restore original paths."""
        try:
            result = shield_manager.deactivate_shield()
            state["shield_active"] = False
            return jsonify({"success": True, **result})
        except Exception as e:
            log.error("Shield deactivation failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/shield/benchmark", methods=["POST"])
    def shield_benchmark():
        """Run write benchmark to measure current SSD activity."""
        import time
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

    @app.route("/api/config", methods=["GET"])
    def get_config():
        """Get app configuration."""
        return jsonify({
            "smartmontools_path": config.smartmontools_path,
            "data_dir": str(config.data_dir),
            "version": "1.0.0",
        })

    # ─── Web UI ────────────────────────────────────────────────────

    @app.route("/")
    def index():
        return render_ui()

    return app


# ─── Embedded Web UI ──────────────────────────────────────────────────────────

# UI is in v2_ui.py (Phase 1–5 Champions / Admin Banner / Share Panel)
from v2_ui import render_ui
