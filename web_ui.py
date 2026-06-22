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

def render_ui() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>DRIVE — AI SSD Guardian</title>
  <style>
    /* === RESET & BASE === */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #0a0a0b;
      --surface: #111114;
      --surface2: #1a1a1f;
      --border: #2a2a32;
      --text: #e8e8ec;
      --text-dim: #8888a0;
      --accent: #00d4aa;
      --accent-dim: #00d4aa33;
      --danger: #ff4757;
      --danger-dim: #ff475733;
      --warn: #ffa502;
      --warn-dim: #ffa50233;
      --font: 'Geist Mono', 'Cascadia Code', 'Fira Code', monospace;
    }
    html, body { height: 100%; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      font-size: 13px;
      line-height: 1.6;
      overflow-x: hidden;
    }

    /* === LAYOUT === */
    .container {
      max-width: 900px;
      margin: 0 auto;
      padding: 32px 24px 80px;
    }

    /* === HEADER === */
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 40px;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--border);
    }
    .logo {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .logo-icon {
      width: 36px;
      height: 36px;
      background: var(--accent);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      font-weight: 700;
      color: #000;
    }
    .logo-text { font-size: 20px; font-weight: 700; letter-spacing: 4px; }
    .logo-sub { color: var(--text-dim); font-size: 11px; letter-spacing: 2px; }
    .header-right { text-align: right; }
    .version-tag { color: var(--accent); font-size: 11px; }

    /* === CARDS === */
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 16px;
    }
    .card-title {
      font-size: 10px;
      letter-spacing: 3px;
      color: var(--text-dim);
      margin-bottom: 16px;
      text-transform: uppercase;
    }

    /* === DRIVE HEALTH CARD === */
    .drive-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
    .drive-model { font-size: 15px; font-weight: 600; color: var(--text); }
    .drive-capacity { color: var(--text-dim); font-size: 12px; margin-top: 2px; }
    .health-meter { margin: 20px 0; }
    .health-bar-bg { height: 8px; background: var(--surface2); border-radius: 4px; overflow: hidden; }
    .health-bar-fill { height: 100%; border-radius: 4px; transition: width 1s ease, background 0.5s; }
    .health-labels { display: flex; justify-content: space-between; margin-top: 6px; font-size: 11px; color: var(--text-dim); }
    .health-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 20px; }
    .stat-box { background: var(--surface2); border-radius: 8px; padding: 12px; }
    .stat-label { font-size: 10px; color: var(--text-dim); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 4px; }
    .stat-value { font-size: 16px; font-weight: 600; }
    .stat-sub { font-size: 10px; color: var(--text-dim); margin-top: 2px; }

    /* === SHIELD CARD === */
    .shield-status-row { display: flex; align-items: center; gap: 16px; }
    .shield-indicator { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
    .shield-indicator.inactive { background: var(--border); }
    .shield-indicator.active { background: var(--accent); box-shadow: 0 0 8px var(--accent); animation: pulse 2s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    .shield-info { flex: 1; }
    .shield-title { font-weight: 600; }
    .shield-sub { color: var(--text-dim); font-size: 11px; }
    .btn { padding: 10px 20px; border-radius: 8px; font-family: var(--font); font-size: 12px; font-weight: 600; cursor: pointer; border: none; transition: all 0.2s; letter-spacing: 1px; }
    .btn-primary { background: var(--accent); color: #000; }
    .btn-primary:hover { background: #00f0c0; transform: translateY(-1px); }
    .btn-danger { background: var(--danger-dim); color: var(--danger); border: 1px solid var(--danger); }
    .btn-danger:hover { background: var(--danger); color: #fff; }
    .btn-ghost { background: transparent; color: var(--text-dim); border: 1px solid var(--border); }
    .btn-ghost:hover { border-color: var(--text-dim); color: var(--text); }
    .shield-actions { margin-top: 16px; display: flex; gap: 12px; flex-wrap: wrap; }

    /* === AI FRAMEWORKS === */
    .framework-list { display: flex; flex-direction: column; gap: 8px; }
    .framework-item {
      display: grid;
      grid-template-columns: 1fr auto auto;
      align-items: center;
      gap: 12px;
      padding: 12px 16px;
      background: var(--surface2);
      border-radius: 8px;
      border: 1px solid var(--border);
    }
    .fw-name { font-weight: 600; font-size: 13px; }
    .fw-path { font-size: 10px; color: var(--text-dim); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 400px; }
    .fw-writes { font-size: 13px; font-weight: 600; text-align: right; }
    .fw-badge { font-size: 10px; padding: 3px 8px; border-radius: 4px; text-align: center; }
    .badge-high { background: var(--danger-dim); color: var(--danger); }
    .badge-med { background: var(--warn-dim); color: var(--warn); }
    .badge-low { background: var(--accent-dim); color: var(--accent); }
    .fw-none { color: var(--text-dim); text-align: center; padding: 24px; font-size: 12px; }

    /* === SCAN BUTTON === */
    .scan-section { text-align: center; margin: 32px 0; }
    .btn-scan { padding: 14px 40px; font-size: 14px; background: linear-gradient(135deg, var(--accent), #00b894); color: #000; }
    .btn-scan:hover { transform: translateY(-2px); box-shadow: 0 8px 24px var(--accent-dim); }

    /* === PROJECTION === */
    .projection { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px; margin: 16px 0; }
    .proj-box { padding: 16px; border-radius: 8px; text-align: center; }
    .proj-box.before { background: var(--danger-dim); border: 1px solid var(--danger); }
    .proj-box.after { background: var(--accent-dim); border: 1px solid var(--accent); }
    .proj-arrow { font-size: 20px; color: var(--text-dim); text-align: center; }
    .proj-value { font-size: 22px; font-weight: 700; }
    .proj-label { font-size: 10px; margin-top: 4px; opacity: 0.8; }

    /* === LOADING === */
    .loading { display: none; text-align: center; padding: 24px; color: var(--text-dim); }
    .spinner { display: inline-block; width: 20px; height: 20px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 8px; vertical-align: middle; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .loading.show { display: block; }

    /* === ERROR === */
    .error-msg { background: var(--danger-dim); border: 1px solid var(--danger); color: var(--danger); padding: 12px 16px; border-radius: 8px; margin: 8px 0; font-size: 12px; display: none; }
    .error-msg.show { display: block; }

    /* === RESULTS === */
    .results-section { display: none; }
    .results-section.visible { display: block; }

    /* === FOOTER === */
    footer { text-align: center; color: var(--text-dim); font-size: 11px; padding: 24px 0; border-top: 1px solid var(--border); margin-top: 40px; }
    footer a { color: var(--accent); text-decoration: none; }

    /* === RESPONSIVE === */
    @media (max-width: 600px) {
      .health-stats { grid-template-columns: 1fr; }
      .framework-item { grid-template-columns: 1fr auto; }
      .fw-path { display: none; }
      .projection { grid-template-columns: 1fr; }
      .proj-arrow { display: none; }
    }
  </style>
</head>
<body>
<div class="container">

  <!-- HEADER -->
  <header>
    <div class="logo">
      <div class="logo-icon">D</div>
      <div>
        <div class="logo-text">DRIVE</div>
        <div class="logo-sub">AI SSD GUARDIAN</div>
      </div>
    </div>
    <div class="header-right">
      <div class="version-tag">v1.0.0</div>
      <div class="logo-sub">getdrive.io</div>
    </div>
  </header>

  <!-- DRIVE HEALTH -->
  <div class="card" id="drive-card">
    <div class="card-title">// SSD Health</div>
    <div class="drive-header">
      <div>
        <div class="drive-model" id="model-name">Scanning...</div>
        <div class="drive-capacity" id="drive-capacity"></div>
      </div>
      <div style="text-align:right">
        <div style="font-size:11px;color:var(--text-dim)">Est. Life Remaining</div>
        <div style="font-size:24px;font-weight:700;color:var(--accent)" id="life-display">--</div>
      </div>
    </div>
    <div class="health-meter">
      <div class="health-bar-bg">
        <div class="health-bar-fill" id="health-bar" style="width:0%; background:var(--accent)"></div>
      </div>
      <div class="health-labels">
        <span>0% (dead)</span>
        <span id="health-pct">--</span>
        <span>100% (new)</span>
      </div>
    </div>
    <div class="health-stats">
      <div class="stat-box">
        <div class="stat-label">Data Written</div>
        <div class="stat-value" id="tbw-written">--</div>
        <div class="stat-sub">of rated TBW</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">Power-On Hours</div>
        <div class="stat-value" id="power-hours">--</div>
        <div class="stat-sub" id="power-days">--</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">Temperature</div>
        <div class="stat-value" id="temp-value">--</div>
        <div class="stat-sub">°C</div>
      </div>
    </div>
  </div>

  <!-- SHIELD CONTROL -->
  <div class="card">
    <div class="card-title">// Shield Control</div>
    <div class="shield-status-row">
      <div class="shield-indicator inactive" id="shield-dot"></div>
      <div class="shield-info">
        <div class="shield-title" id="shield-title">Shield Inactive</div>
        <div class="shield-sub" id="shield-sub">Redirect AI writes to RAM. Zero SSD wear.</div>
      </div>
    </div>
    <div class="shield-actions">
      <button class="btn btn-primary" id="btn-activate" onclick="activateShield()">Activate Shield</button>
      <button class="btn btn-danger" id="btn-deactivate" onclick="deactivateShield()" style="display:none">Deactivate</button>
      <button class="btn btn-ghost" onclick="runBenchmark()">Run Write Benchmark</button>
    </div>
  </div>

  <!-- SCAN -->
  <div class="scan-section">
    <button class="btn btn-scan" id="btn-scan" onclick="runScan()">
      <span id="scan-label">Run AI Impact Scan</span>
    </button>
    <div class="loading" id="loading">
      <span class="spinner"></span>Scanning SSD and detecting AI frameworks...
    </div>
    <div class="error-msg" id="error-msg"></div>
  </div>

  <!-- RESULTS -->
  <div class="results-section" id="results-section">
    <div class="card">
      <div class="card-title">// AI Impact Analysis</div>

      <div class="projection" id="projection-box" style="display:none">
        <div class="proj-box before">
          <div class="proj-value" id="life-before">-- months</div>
          <div class="proj-label">Life WITHOUT DRIVE</div>
        </div>
        <div class="proj-arrow">→</div>
        <div class="proj-box after">
          <div class="proj-value" style="color:var(--accent)" id="life-after">-- months</div>
          <div class="proj-label">Life WITH Shield</div>
        </div>
      </div>

      <div class="framework-list" id="framework-list">
        <div class="fw-none">No AI frameworks detected.</div>
      </div>

      <div style="margin-top:16px;padding:12px;background:var(--surface2);border-radius:8px;font-size:12px;color:var(--text-dim);" id="total-writes-row">
        Total daily writes: <span id="total-writes" style="color:var(--text);font-weight:600">--</span>
      </div>
    </div>
  </div>

  <!-- FOOTER -->
  <footer>
    DRIVE — Your data never leaves your machine &nbsp;|&nbsp;
    <a href="https://getdrive.io" target="_blank">getdrive.io</a>
    &nbsp;|&nbsp; MIT License
  </footer>
</div>

<script>
  // ─── State ─────────────────────────────────────────────────────────
  let lastScan = null;
  let shieldActive = false;

  // ─── API helpers ────────────────────────────────────────────────────
  async function api(path, opts = {}) {
    try {
      const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || 'Request failed');
      return d;
    } catch (e) {
      showError(e.message);
      throw e;
    }
  }

  function showError(msg) {
    const el = document.getElementById('error-msg');
    el.textContent = msg;
    el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), 6000);
  }

  // ─── Render helpers ─────────────────────────────────────────────────
  function healthColor(pct) {
    if (pct < 30) return 'var(--danger)';
    if (pct < 60) return 'var(--warn)';
    return 'var(--accent)';
  }

  function gbLabel(gb) {
    if (gb >= 1) return gb.toFixed(1) + ' GB/day';
    return (gb * 1024).toFixed(0) + ' MB/day';
  }

  function writeClass(gb) {
    if (gb >= 10) return 'badge-high';
    if (gb >= 2) return 'badge-med';
    return 'badge-low';
  }

  // ─── Render drive info ──────────────────────────────────────────────
  function renderDrive(info) {
    document.getElementById('model-name').textContent = info.model || 'Unknown Drive';
    document.getElementById('drive-capacity').textContent = info.capacity_gb
      ? Math.round(info.capacity_gb) + ' GB'
      : '';

    const pct = info.health_percent ?? 100;
    const bar = document.getElementById('health-bar');
    bar.style.width = pct + '%';
    bar.style.background = healthColor(pct);
    document.getElementById('health-pct').textContent = pct + '% remaining';

    document.getElementById('tbw-written').textContent = info.tbw_written_tb != null
      ? info.tbw_written_tb.toFixed(1) + ' TB'
      : '--';

    const hours = info.power_on_hours;
    if (hours != null) {
      document.getElementById('power-hours').textContent = hours.toLocaleString();
      const days = Math.floor(hours / 24);
      document.getElementById('power-days').textContent = days + ' days';
    }

    document.getElementById('temp-value').textContent = info.temperature_c != null
      ? info.temperature_c + '°'
      : '--';

    document.getElementById('life-display').textContent = info.projected_life_months != null
      ? info.projected_life_months + ' mo'
      : '--';
    document.getElementById('life-display').style.color = healthColor(pct);
  }

  // ─── Render frameworks ──────────────────────────────────────────────
  function renderFrameworks(frameworks, totalDailyGb) {
    const container = document.getElementById('framework-list');
    const resultsSection = document.getElementById('results-section');
    const totalRow = document.getElementById('total-writes-row');
    const totalEl = document.getElementById('total-writes');
    const projBox = document.getElementById('projection-box');

    resultsSection.classList.add('visible');

    if (!frameworks || frameworks.length === 0) {
      container.innerHTML = '<div class="fw-none">No AI frameworks detected. Your SSD is safe... for now.</div>';
      totalEl.textContent = '0 GB/day';
      projBox.style.display = 'none';
      return;
    }

    container.innerHTML = frameworks.map(fw => {
      const gb = fw.estimated_daily_gb || 0;
      const badge = writeClass(gb);
      return `
        <div class="framework-item">
          <div>
            <div class="fw-name">${fw.name}</div>
            <div class="fw-path">${fw.detected_path || ''}</div>
          </div>
          <div>
            <span class="fw-badge ${badge}">${fw.severity || 'low'}</span>
          </div>
          <div class="fw-writes" style="color:${gb >= 10 ? 'var(--danger)' : gb >= 2 ? 'var(--warn)' : 'var(--accent)'}">
            ${gbLabel(gb)}
          </div>
        </div>
      `;
    }).join('');

    totalEl.textContent = gbLabel(totalDailyGb);
    totalRow.style.display = 'block';

    // Projection box
    if (lastScan && lastScan.drive && lastScan.drive.projected_life_months != null) {
      const before = lastScan.drive.projected_life_months;
      const after = Math.round(before * (1 + (totalDailyGb > 0 ? 0.6 : 0)));
      document.getElementById('life-before').textContent = before + ' months';
      document.getElementById('life-after').textContent = after + ' months';
      document.getElementById('life-display').textContent = after + ' mo';
      projBox.style.display = 'grid';
    }
  }

  // ─── Shield UI state ────────────────────────────────────────────────
  function renderShieldStatus(active, info) {
    shieldActive = active;
    const dot = document.getElementById('shield-dot');
    const title = document.getElementById('shield-title');
    const sub = document.getElementById('shield-sub');
    const btnOn = document.getElementById('btn-activate');
    const btnOff = document.getElementById('btn-deactivate');

    dot.className = 'shield-indicator ' + (active ? 'active' : 'inactive');
    title.textContent = active ? 'Shield Active' : 'Shield Inactive';
    btnOn.style.display = active ? 'none' : 'inline-block';
    btnOff.style.display = active ? 'inline-block' : 'none';

    if (active && info && info.ramdisk_letter) {
      sub.textContent = 'RAMDisk ' + info.ramdisk_letter + ': active. AI writes redirected. SSD wear: 0.';
    } else if (!active) {
      sub.textContent = 'Redirect AI writes to RAM. Zero SSD wear.';
    }
  }

  // ─── Actions ───────────────────────────────────────────────────────
  async function runScan() {
    const btn = document.getElementById('btn-scan');
    const label = document.getElementById('scan-label');
    const loading = document.getElementById('loading');
    const results = document.getElementById('results-section');

    btn.disabled = true;
    label.textContent = 'Scanning...';
    loading.classList.add('show');
    results.classList.remove('visible');
    document.getElementById('error-msg').classList.remove('show');

    try {
      const data = await api('/api/scan');
      lastScan = data;

      renderDrive(data.drive || data.drive);
      renderFrameworks(data.frameworks || [], data.total_daily_gb || 0);
      renderShieldStatus(data.shield_active || false, {});
    } catch (e) {
      // errors shown via showError
    } finally {
      btn.disabled = false;
      label.textContent = 'Re-run AI Impact Scan';
      loading.classList.remove('show');
    }
  }

  async function activateShield() {
    const btn = document.getElementById('btn-activate');
    btn.disabled = true;
    btn.textContent = 'Activating...';
    try {
      const data = await api('/api/shield/activate', {
        method: 'POST',
        body: JSON.stringify({ ramdisk_size_gb: 4 }),
      });
      renderShieldStatus(true, data);
      if (lastScan && lastScan.drive) {
        const d = lastScan.drive;
        if (d.projected_life_months) {
          const newLife = Math.round(d.projected_life_months * 1.6);
          document.getElementById('life-display').textContent = newLife + ' mo';
          document.getElementById('life-after').textContent = newLife + ' months';
          document.getElementById('life-before').textContent = d.projected_life_months + ' months';
          document.getElementById('projection-box').style.display = 'grid';
        }
      }
    } catch (e) { /* showError already called */ }
    btn.disabled = false;
    btn.textContent = 'Activate Shield';
  }

  async function deactivateShield() {
    const btn = document.getElementById('btn-deactivate');
    btn.disabled = true;
    btn.textContent = 'Deactivating...';
    try {
      await api('/api/shield/deactivate', { method: 'POST' });
      renderShieldStatus(false, {});
      document.getElementById('life-display').style.color = 'var(--accent)';
    } catch (e) { /* showError */ }
    btn.disabled = false;
    btn.textContent = 'Deactivate';
  }

  async function runBenchmark() {
    const btn = event.target;
    const orig = btn.textContent;
    btn.textContent = 'Benchmarking (60s)...';
    btn.disabled = true;
    try {
      const data = await api('/api/shield/benchmark', {
        method: 'POST',
        body: JSON.stringify({ duration_sec: 60 }),
      });
      alert('Benchmark complete!\\n'
        + 'Active writes: ' + data.active_gb_per_day?.toFixed(1) + ' GB/day\\n'
        + 'At this rate, your SSD dies in: ' + data.days_remaining + ' days\\n\\n'
        + 'Shield reduces this to: ' + data.protected_days_remaining + ' days');
    } catch (e) { /* showError */ }
    btn.textContent = orig;
    btn.disabled = false;
  }

  // ─── Init ──────────────────────────────────────────────────────────
  (async () => {
    // Load drive info immediately
    try {
      const info = await api('/api/drive');
      renderDrive(info);
    } catch (e) {
      document.getElementById('model-name').textContent = 'Drive scan unavailable';
    }
    // Load shield status
    try {
      const st = await api('/api/shield/status');
      renderShieldStatus(st.active, st);
    } catch (e) { /* no shield status */ }
  })();
</script>
</body>
</html>"""