"""
DRIVE — AI SSD Guardian
Flask application factory.
Flask import is deferred to runtime (lazy import).
This avoids breaking tests that only need models/config/path_scanner.
"""
from __future__ import annotations

import logging
import platform
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
    process_inspector = None  # imported lazily
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
            "version": "1.1.0",
            "shield_active": state["shield_active"],
            "platform": platform.system(),
        })

    # ─── SSD Scan ─────────────────────────────────────────────────────

    @app.route("/api/scan", methods=["GET"])
    def scan():
        """Run full SSD health + AI impact scan.

        Combines:
        - SMART data via smartctl (if installed) or WMI fallback
        - Real running process detection
        - 5-second observed writes sample to known framework dirs
        """
        start = time.time()

        # Smart data
        try:
            drive_info = smart_reader.get_drive_info()
        except Exception as e:
            log.error("SMART read failed: %s", e)
            drive_info = DriveInfo(model="Unknown")

        # Lazy import process_inspector (so we surface a cleaner traceback)
        from process_inspector import (
            detect_ai_processes,
            measure_framework_disk_usage,
            sample_framework_writes,
            DetectedProcess,
        )
        sample_seconds = float(request.args.get("sample_seconds", 5.0))
        sample_seconds = max(2.0, min(sample_seconds, 30.0))
        log.info("Running %ss sample to measure real writes", sample_seconds)

        # Detect running AI processes
        ai_processes = detect_ai_processes()
        for p in ai_processes:
            p.to_dict = lambda _self=p: _self.__dict__  # convenience, then overwritten below

        # Sample framework dirs (full 5s)
        try:
            measured_writes = sample_framework_writes(seconds=sample_seconds)
        except Exception as e:
            log.error("Write sample failed: %s", e)
            measured_writes = {}

        # Combine: focus on detected frameworks + measured dirs
        framework_dicts = []
        seen_labels = set()

        for p in ai_processes:
            label = p.label
            if label in seen_labels:
                continue
            seen_labels.add(label)

            # Pair the process with measured writes by label family substrings
            label_key = label.split(" ")[0].lower()
            measured_rate = 0.0
            for ml, rate in measured_writes.items():
                if any(word.lower() in label_key for word in ml.split()):
                    measured_rate += rate
                    break

            daily_gb = (measured_rate * 86400) / (1024**3) if measured_rate > 0 else p.severity_gb_per_day

            framework_dicts.append({
                "id": label_key,
                "name": label,
                "detected_path": p.image_path,
                "is_running": True,
                "pid": p.pid,
                "process_name": p.name,
                "cmdline": p.cmdline_match or "",
                "estimated_daily_gb": round(daily_gb, 2),
                "measured_bytes_per_sec": round(measured_rate, 1) if measured_rate > 0 else None,
                "severity": (
                    "high" if daily_gb >= 10
                    else "medium" if daily_gb >= 2
                    else "low"
                ),
                "source": "process+measurement" if measured_rate > 0 else "process+estimate",
            })

        # Add dirs that are growing on disk even if we didn't see the process
        for label, rate in measured_writes.items():
            if any(label in f.get("name", "") for f in framework_dicts):
                continue
            label_key = label.split(" ")[0].lower()
            daily_gb = (rate * 86400) / (1024**3)
            if daily_gb >= 0.5:  # ignore noise <0.5GB/day
                framework_dicts.append({
                    "id": label_key,
                    "name": label,
                    "detected_path": "(sampled on disk)",
                    "is_running": False,
                    "pid": None,
                    "process_name": None,
                    "cmdline": "",
                    "estimated_daily_gb": round(daily_gb, 2),
                    "measured_bytes_per_sec": round(rate, 1),
                    "severity": ("high" if daily_gb >= 10 else "medium" if daily_gb >= 2 else "low"),
                    "source": "measurement-only",
                })

        # Disk-on-disk usage of known framework dirs (independent stat)
        on_disk = measure_framework_disk_usage()

        total_daily_gb = sum(f["estimated_daily_gb"] for f in framework_dicts)
        if total_daily_gb > 0:
            drive_info.projected_life_months = drive_info.estimate_life_months(total_daily_gb)

        is_shield = shield_manager.is_shield_active()
        state["shield_active"] = is_shield

        result = {
            "drive": drive_info.to_dict(),
            "frameworks": framework_dicts,
            "total_daily_gb": round(total_daily_gb, 3),
            "shield_active": is_shield,
            "scan_duration_ms": int((time.time() - start) * 1000),
            "sample_seconds": sample_seconds,
            "framework_disk_usage_bytes": on_disk,
            "ai_process_count": len(ai_processes),
            "respecting_uncertainty": True,
        }
        state["last_scan"] = result
        return jsonify(result)

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
                frameworks=state["last_scan"].get("frameworks") if state["last_scan"] else None,
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
                frameworks=state["last_scan"].get("frameworks") if state["last_scan"] else None,
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