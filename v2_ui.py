"""
DRIVE v1.2.0 — UI module (embedded HTML page).
Returns the full self-contained dashboard with honest Shield status,
admin elevation banner, Champions license modal, and share buttons.
"""
from __future__ import annotations

GUMROAD_URL = "https://diegoevillarroel.gumroad.com/l/ai-drive-smooth"


def render_ui() -> str:
    return _UI_HTML


_UI_HTML: str = ""  # populated below to keep file parseable


_UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>DRIVE — AI SSD Guardian</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0a0a0b;--surface:#111114;--surface2:#1a1a1f;--border:#2a2a32;
  --text:#e8e8ec;--text-dim:#8888a0;--accent:#00d4aa;--accent-dim:#00d4aa33;
  --danger:#ff4757;--warn:#ffa502;--font:'Segoe UI',system-ui,monospace;
}
body{background:var(--bg);color:var(--text);font-family:var(--font);font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}
.container{max-width:960px;margin:0 auto;padding:24px 20px}
header{display:flex;align-items:center;gap:16px;margin-bottom:24px;flex-wrap:wrap}
.logo{background:var(--accent);color:#000;padding:6px 14px;border-radius:6px;font-weight:700;font-size:18px;letter-spacing:1px}
.badge{font-size:10px;color:var(--text-dim);letter-spacing:2px;text-transform:uppercase}
h2{font-size:13px;letter-spacing:2px;color:var(--text-dim);margin-bottom:14px;text-transform:uppercase}
a{color:var(--accent);text-decoration:none}
.btn{
  background:var(--surface2);color:var(--text);border:1px solid var(--border);
  padding:10px 18px;border-radius:8px;cursor:pointer;font-family:var(--font);
  font-size:13px;font-weight:600;letter-spacing:0.5px;transition:.15s;
}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn-primary{background:var(--accent);color:#000;border-color:var(--accent);font-weight:700}
.btn-primary:hover{background:#00e0b0}
.btn-sm{padding:6px 12px;font-size:11px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:16px}
.stat-row{display:flex;gap:12px;flex-wrap:wrap}
.stat{background:var(--surface2);border-radius:8px;padding:16px;flex:1;min-width:120px}
.stat-label{font-size:10px;letter-spacing:2px;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px}
.stat-value{font-size:22px;font-weight:700}
.stat-value.accent{color:var(--accent)}
.stat-value.danger{color:var(--danger)}
.fw-item{
  display:grid;grid-template-columns:1fr 100px 80px auto;gap:10px;align-items:center;
  padding:10px 12px;background:var(--surface2);border-radius:6px;margin-bottom:6px;font-size:12px;
}
.fw-name{font-weight:600}
.fw-gb{text-align:right;font-weight:600}
.fw-sev{text-align:center;font-size:10px;letter-spacing:1px;text-transform:uppercase}
.sev-high{color:var(--danger)}.sev-med{color:var(--warn)}.sev-low{color:var(--text-dim)}
.fw-conf{text-align:right;font-size:10px;color:var(--text-dim)}
.source-badge{
  display:inline-block;padding:1px 5px;border-radius:3px;font-size:8px;letter-spacing:1px;
  text-transform:uppercase;margin-left:4px;
}
.source-badge.measured{background:var(--accent-dim);color:var(--accent)}
.source-badge.estimated{background:#8888a025;color:var(--text-dim)}
.source-badge.unsourced{background:#ff475720;color:var(--danger)}
/* ADMIN BANNER */
.admin-banner{
  display:none;background:linear-gradient(135deg,#2a1a00,#1a1100);
  border:1px solid var(--warn);border-radius:8px;padding:12px 16px;
  margin-bottom:14px;font-size:12px;color:var(--warn);align-items:center;gap:12px;
}
.admin-banner.shown{display:flex}
.admin-banner .bn-text{flex:1;line-height:1.5}
.admin-banner .bn-btn{background:var(--warn);color:#000;border:none;padding:6px 12px;
  border-radius:6px;font-weight:700;font-size:11px;cursor:pointer;font-family:var(--font)}
/* SHIELD PANEL */
.shield-panel.card{border-left:4px solid var(--border)}
.shield-panel.shield-active{border-left-color:var(--accent);background:linear-gradient(135deg,#00d4aa08,var(--surface))}
.shield-panel.shield-fail{border-left-color:var(--danger);background:linear-gradient(135deg,#ff475708,var(--surface))}
.shield-panel.shield-pending{border-left-color:var(--warn)}
.shield-row{display:flex;align-items:center;gap:12px}
.shield-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0;background:var(--border)}
.shield-dot.active{background:var(--accent);box-shadow:0 0 8px var(--accent);animation:pulse 2s infinite}
.shield-dot.fail{background:var(--danger)}
.shield-dot.pending{background:var(--warn)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.shield-msg{font-size:12px;color:var(--text-dim);margin-top:8px;line-height:1.6}
.shield-error{background:#ff475715;border-left:3px solid var(--danger);padding:8px 10px;margin-top:10px;border-radius:4px;font-size:11px;color:#ff7e8a}
.shield-success{background:#00d4aa12;border-left:3px solid var(--accent);padding:8px 10px;margin-top:10px;border-radius:4px;font-size:11px;color:#6ee6cb}
.shield-actions{margin-top:12px;display:flex;gap:8px;flex-wrap:wrap}
/* MODAL */
.modal-overlay{
  display:none;position:fixed;inset:0;background:#000c;backdrop-filter:blur(8px);
  z-index:1000;align-items:center;justify-content:center;padding:20px;
}
.modal-overlay.shown{display:flex}
.modal-box{
  background:linear-gradient(135deg,#14141a,#1a1a1f);border:1px solid var(--accent);
  border-radius:16px;padding:36px;max-width:540px;width:100%;position:relative;
}
.modal-close{position:absolute;top:12px;right:14px;color:var(--text-dim);cursor:pointer;font-size:18px;line-height:1}
.modal-title{font-size:12px;letter-spacing:4px;color:var(--accent);font-weight:700;margin-bottom:14px}
.modal-headline{font-size:26px;font-weight:700;line-height:1.3;margin-bottom:14px}
.modal-headline em{color:var(--accent);font-style:normal}
.modal-detail{font-size:13px;line-height:1.7;color:var(--text-dim);margin-bottom:20px}
.modal-stats{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:24px}
.modal-stat{background:var(--surface2);border-radius:8px;padding:12px}
.modal-stat-label{font-size:9px;letter-spacing:2px;color:var(--text-dim);text-transform:uppercase;margin-bottom:4px}
.modal-stat-value{font-size:18px;font-weight:700}
.modal-price{display:flex;align-items:baseline;gap:10px;margin-bottom:20px}
.modal-price-now{font-size:36px;font-weight:700;color:var(--accent)}
.modal-price-once{font-size:12px;color:var(--text-dim)}
.modal-cta{
  width:100%;background:linear-gradient(135deg,#00d4aa,#00b894);color:#000;
  padding:16px;border-radius:10px;text-align:center;font-weight:700;font-size:15px;
  letter-spacing:1px;cursor:pointer;border:none;font-family:var(--font);
}
.modal-cta:hover{transform:translateY(-1px);box-shadow:0 6px 18px #00d4aa44}
.modal-input{
  width:100%;background:var(--surface2);border:1px solid var(--border);color:var(--text);
  padding:12px;border-radius:8px;font-family:var(--font);font-size:13px;margin-top:10px;letter-spacing:1px;
}
.modal-input:focus{outline:none;border-color:var(--accent)}
.modal-fineprint{font-size:10px;color:var(--text-dim);text-align:center;margin-top:12px;line-height:1.5}
.modal-secondary{
  width:100%;background:transparent;color:var(--text-dim);padding:12px;border-radius:10px;
  border:1px solid var(--border);cursor:pointer;font-size:12px;font-family:var(--font);margin-top:8px;
}
.modal-secondary:hover{color:var(--text);border-color:var(--text-dim)}
/* SHARE */
.share-row{display:flex;gap:6px;margin:12px 0;flex-wrap:wrap}
.share-btn{background:var(--surface2);color:var(--text);border:1px solid var(--border);
  padding:6px 12px;border-radius:6px;font-size:10px;cursor:pointer;font-family:var(--font);letter-spacing:1px}
.share-btn:hover{border-color:var(--accent);color:var(--accent)}
/* resp */
@media(max-width:600px){
  .fw-item{grid-template-columns:1fr 70px 60px auto}
  .modal-stats{grid-template-columns:1fr}
}
</style>
</head>
<body>
<div class="container">
<header>
  <span class="logo">DRIVE</span>
  <span class="badge">AI SSD Guardian v1.2.0</span>
</header>

<!-- ADMIN BANNER -->
<div id="admin-banner" class="admin-banner" style="display:none">
  <span class="bn-text">Shield requires one-time admin setup. DRIVE will handle the UAC prompt.</span>
  <button class="bn-btn" onclick="elevate()">Run as Admin</button>
</div>

<!-- SHIELD PANEL (honest states) -->
<div id="shield-panel" class="shield-panel card">
  <h2>SHIELD STATUS</h2>
  <div class="shield-row">
    <span id="shield-dot" class="shield-dot inactive"></span>
    <span id="shield-state-text" style="font-weight:700">Loading...</span>
  </div>
  <div class="shield-msg" id="shield-meta"></div>
  <div id="shield-detail"></div>
  <div class="shield-actions">
    <button id="shield-btn" class="btn btn-primary" onclick="activateShield()">Activate Shield</button>
    <button class="btn btn-sm" onclick="fetchShieldStatus()">Refresh</button>
  </div>
</div>

<!-- DRIVE HEALTH -->
<div class="card" id="health-card">
  <h2>SSD HEALTH</h2>
  <div id="health-content">Loading...</div>
</div>

<!-- SCAN -->
<div class="card">
  <h2>AI ACTIVITY SCANNER</h2>
  <button class="btn btn-primary" onclick="runScan()">Run Scan</button>
  <span style="margin-left:12px;font-size:12px;color:var(--text-dim)" id="scan-status"></span>
  <div id="frameworks" style="margin-top:14px"></div>
</div>

<!-- RESULTS -->
<div id="results" style="margin-top:14px"></div>

<!-- SHARE -->
<div class="share-row">
  <button class="share-btn" onclick="copyReport()">Copy Report</button>
  <a class="share-btn" href="/api/share/card.png" download="drive-report.png" style="text-decoration:none">Save PNG</a>
  <a class="share-btn" href="/api/share/card.svg" download="drive-report.svg">Save SVG</a>
</div>

<!-- FOOTER -->
<div style="text-align:center;margin-top:24px;font-size:11px;color:var(--text-dim)">
  DRIVE v1.2.0 — Shield stops your SSD from dying. One-time purchase, lifetime protection. &nbsp;
  <a href="https://diegoevillarroel.gumroad.com/l/ai-drive-smooth" target="_blank">Get DRIVE — $14.99</a>
</div>
</div>

<!-- CHAMPIONS LICENSE MODAL -->
<div id="modal-overlay" class="modal-overlay">
<div class="modal-box">
  <span class="modal-close" onclick="closeModal()">&times;</span>
  <div class="modal-title">DRIVE SHIELD — LICENSE REQUIRED</div>
  <div class="modal-headline">
    Your SSD has <em id="modal-months">?</em> months left<br>at current AI write rate.
  </div>
  <div class="modal-detail">
    The Shield intercepts AI writes and redirects them to a RAM disk.<br>
    Your SSD stops aging at 50x normal speed.<br>
    <strong>Activating Shield stops this now.</strong>
  </div>
  <div class="modal-stats">
    <div class="modal-stat">
      <div class="modal-stat-label">YOUR SSD</div>
      <div class="modal-stat-value" id="modal-model">?</div>
    </div>
    <div class="modal-stat">
      <div class="modal-stat-label">DAILY WRITES</div>
      <div class="modal-stat-value" id="modal-daily">?</div>
    </div>
  </div>
  <div class="modal-price">
    <span class="modal-price-now">$14.99</span>
    <span class="modal-price-once">One-time. No subscription. Lifetime updates.</span>
  </div>
  <input class="modal-input" id="license-key-input" placeholder="Paste your Gumroad license key..." autocomplete="off"/>
  <button class="modal-cta" onclick="submitLicense()">ACTIVATE SHIELD</button>
  <button class="modal-secondary" onclick="window.open('https://diegoevillarroel.gumroad.com/l/ai-drive-smooth','_blank')">
    Don't have a license? Buy one now ($14.99)
  </button>
  <div class="modal-fineprint">
    License sent to your Gumroad email instantly after purchase.<br>
    One key = all your computers. No phone-home check except weekly re-verification.
  </div>
</div>
</div>

<script>
// ─── Globals ────────────────────────────────────────────────────
let lastScan = {}, shieldState = {state:'not_attempted'};

// ─── Fetch helpers ──────────────────────────────────────────────
async function api(url, opts={}) {
  const r = await fetch(url, opts);
  if (!r.ok) return r.json().catch(()=>({error:r.status}));
  return r.json();
}

// ─── Shield status (honest) ─────────────────────────────────────
async function fetchShieldStatus() {
  const d = await api('/api/shield/status');
  shieldState = d;
  renderShield(d);
  // Also update admin banner
  const banner = document.getElementById('admin-banner');
  banner.style.display = (d.state === 'needs_admin_setup' || d.error_code === 'not_admin') ? 'flex' : 'none';
}

function renderShield(s) {
  const dot = document.getElementById('shield-dot');
  const txt = document.getElementById('shield-state-text');
  const meta = document.getElementById('shield-meta');
  const detail = document.getElementById('shield-detail');
  const btn = document.getElementById('shield-btn');
  const panel = document.getElementById('shield-panel');

  dot.className = 'shield-dot ' + (s.active?'active':s.state==='active'?'active':s.state.includes('fail')||s.state==='broken'||s.state==='needs_imdisk'?'fail':'inactive');
  panel.className = 'shield-panel card ' + (s.active?'shield-active':s.error_code?'shield-fail':'');

  const labels = {
    active:'Shield Active — RAMDisk verified. AI writes redirected.',
    not_attempted:'Shield not activated yet. Click below to set it up.',
    needs_imdisk:'ImDisk driver needs installation. Click Activate to auto-install.',
    needs_admin_setup:'Shield needs one-time admin privileges. Click below.',
    needs_elevation:'Admin elevation required.',
    broken:'Shield state is inconsistent. Click Activate to repair.',
    redirects_failed:'RAM installed but redirects lost. Click Activate to repair.',
    driver_load_failed:'Driver mount failed. Reboot and try again.',
    format_failed:'RAM disk format failed. Try a different drive letter.',
    needs_license:'License required to use Shield.',
  };
  txt.textContent = labels[s.state] || s.state;
  meta.innerHTML = s.active
    ? `RAM: ${s.ramdisk_letter}: (${s.ramdisk_free_gb} GB free) | ${s.redirected_count} frameworks protected`
    : (s.error_message || '');
  let det = '';
  if (s.error_message) det += '<div class="shield-error">' + s.error_message + '</div>';
  if (s.next_step) det += '<div class="shield-msg">' + s.next_step + '</div>';
  if (s.active) det += '<div class="shield-success">Verified: mount confirmed by OS, junctions active.</div>';
  detail.innerHTML = det;
  btn.textContent = s.active ? 'Deactivate Shield' : 'Activate Shield';
  btn.onclick = s.active ? deactivateShield : activateShield;
}

async function activateShield() {
  // Check license first
  const lic = await api('/api/license/status');
  if (lic.state === 'none') return showModal();
  if (lic.state === 'verified_fresh' || lic.state === 'verification_due') {
    const r = await api('/api/shield/activate', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ramdisk_size_gb:4})});
    await fetchShieldStatus();
    return;
  }
  showModal();
}

async function deactivateShield() {
  await api('/api/shield/deactivate', {method:'POST'});
  await fetchShieldStatus();
}

async function elevate() {
  await api('/api/admin/elevate', {method:'POST'});
}

// ─── License modal ──────────────────────────────────────────────
function showModal() {
  const m = document.getElementById('modal-overlay');
  m.classList.add('shown');
  // Populate with last scan data
  const d = lastScan.drive || {};
  const months = d.projected_life_months;
  const monthsVal = typeof months === 'number' ? months : 0;
  document.getElementById('modal-months').textContent = monthsVal > 0 ? monthsVal : '?';
  document.getElementById('modal-model').textContent = d.model || 'unknown';
  document.getElementById('modal-daily').textContent = (lastScan.total_daily_gb||0).toFixed(1)+' GB/day';

  // Dynamic severity-based messaging
  const headline = document.querySelector('.modal-headline');
  const detail  = document.querySelector('.modal-detail');
  if (monthsVal > 0 && monthsVal < 24) {
    // ALARMING — critical life remaining
    headline.innerHTML = 'Your SSD has <em style="color:var(--danger)">' + monthsVal + ' months</em> left.<br>Act now before it dies.';
    detail.innerHTML = '<strong style="color:var(--danger)">Your SSD is in critical danger.</strong> AI frameworks are burning through writes at ' +
      ((lastScan.total_daily_gb)||0).toFixed(1) + ' GB/day.<br>' +
      'The Shield intercepts AI writes and redirects them to a RAM disk.<br>' +
      'Your SSD stops aging at 50x normal speed.<br>' +
      '<strong style="color:var(--danger)">Activate now — you may not have another chance.</strong>';
  } else if (monthsVal >= 24 && monthsVal <= 60) {
    // WARNING — moderate life remaining
    headline.innerHTML = 'Your SSD has <em style="color:var(--warn)">' + monthsVal + ' months</em> left<br>at current AI write rate.';
    detail.innerHTML = '<strong style="color:var(--warn)">Your SSD is wearing down faster than expected.</strong> AI frameworks are burning through writes at ' +
      ((lastScan.total_daily_gb)||0).toFixed(1) + ' GB/day.<br>' +
      'The Shield intercepts AI writes and redirects them to a RAM disk.<br>' +
      'Your SSD stops aging at 50x normal speed.<br>' +
      '<strong>Lock in your protection today — before it\'s too late.</strong>';
  } else {
    // CALM — healthy life remaining (>60 months or unknown)
    headline.innerHTML = 'Your SSD has <em>' + (monthsVal > 0 ? monthsVal + ' months' : 'time') + '</em> left.<br>Keep it that way.';
    detail.innerHTML = 'AI frameworks writing at ' +
      ((lastScan.total_daily_gb)||0).toFixed(1) + ' GB/day will wear your SSD over time.<br>' +
      'The Shield intercepts AI writes and redirects them to a RAM disk.<br>' +
      'Your SSD stops aging at 50x normal speed.<br>' +
      '<strong>Activate Shield now to lock in your SSD\'s remaining life.</strong>';
  }
}
function closeModal() { document.getElementById('modal-overlay').classList.remove('shown'); }

async function submitLicense() {
  const key = document.getElementById('license-key-input').value.trim();
  if (!key) return alert('Paste your license key.');
  const r = await api('/api/license/activate', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({license_key:key})});
  if (r.state === 'verified_fresh') {
    closeModal();
    // Now activate shield with the verified license
    const sr = await api('/api/shield/activate', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ramdisk_size_gb:4,license_key:key})});
    if (!sr.active && sr.state === 'needs_license') {
      showModal(); // license didn't take — re-prompt
      return;
    }
    await fetchShieldStatus();
  } else {
    alert(r.message || 'Invalid license key.');
  }
}

// ─── Scan ───────────────────────────────────────────────────────
async function runScan() {
  document.getElementById('scan-status').textContent = 'Scanning...';
  const d = await api('/api/scan?sample_seconds=6');
  lastScan = d;
  renderHealth(d.drive);
  renderFrameworks(d.frameworks, d.total_daily_gb);
  document.getElementById('scan-status').textContent = 'Done ('+d.scan_duration_ms+'ms)';
  await fetchShieldStatus();
}

function renderHealth(d) {
  const h = d.health_percent;
  const healthStr = typeof h === 'number' ? h+'%' : d.smartctl_found ? 'unreadable' : 'smartctl not available';
  const months = d.projected_life_months;
  const monthsStr = typeof months === 'number' ? months+' months' : '?';
  document.getElementById('health-card').innerHTML = '<h2>SSD HEALTH</h2>'+
    '<div class="stat-row">'+
      '<div class="stat"><div class="stat-label">MODEL</div><div class="stat-value" style="font-size:14px">'+(d.model||'?')+'</div></div>'+
      '<div class="stat"><div class="stat-label">HEALTH</div><div class="stat-value '+(typeof h==='number'&&h>80?'accent':'danger')+'">'+healthStr+'</div></div>'+
      '<div class="stat"><div class="stat-label">EST. LIFE</div><div class="stat-value accent">'+monthsStr+'</div></div>'+
      '<div class="stat"><div class="stat-label">CAPACITY</div><div class="stat-value">'+(d.capacity_gb||'?')+' GB</div></div>'+
    '</div>';
}

function renderFrameworks(fws, totalGb) {
  if (!fws || !fws.length) {
    document.getElementById('frameworks').innerHTML = '<div style="color:var(--text-dim);font-size:12px">No AI frameworks detected running.</div>';
    document.getElementById('results').innerHTML = '';
    return;
  }
  let html = '';
  fws.forEach(f=>{
    const sev = f.severity||'low';
    const conf = f.confidence||'estimated';
    const badge = '<span class="source-badge '+conf+'">'+(conf==='measured'?'MEASURED':conf==='unsourced'?'UNSOURCED':'EST')+'</span>';
    html += '<div class="fw-item">'+
      '<div class="fw-name">'+f.name+badge+'</div>'+
      '<div class="fw-gb">'+f.estimated_daily_gb.toFixed(1)+' GB/d</div>'+
      '<div class="fw-sev sev-'+sev+'">'+sev+'</div>'+
      '<div class="fw-conf">'+(f.measured_bytes_per_sec?'live':'est')+'</div>'+
    '</div>';
  });
  document.getElementById('frameworks').innerHTML = html;
  document.getElementById('results').innerHTML = '<div class="stat-row">'+
    '<div class="stat"><div class="stat-label">TOTAL AI WRITES</div><div class="stat-value danger">'+totalGb.toFixed(1)+' GB/day</div></div>'+
    '<div class="stat"><div class="stat-label">FRAMEWORKS</div><div class="stat-value">'+fws.length+'</div></div>'+
  '</div>';
}

// ─── Share ──────────────────────────────────────────────────────
async function copyReport() {
  const r = await api('/api/share/text');
  await navigator.clipboard.writeText(r.text||r);
  const btn = event.target;
  btn.textContent = 'Copied!';
  setTimeout(()=>btn.textContent='Copy Report',1500);
}

// ─── Init ───────────────────────────────────────────────────────
fetchShieldStatus();
runScan();
</script>
</body>
</html>"""