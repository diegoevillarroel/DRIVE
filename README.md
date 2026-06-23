# DRIVE — AI SSD Guardian

<div align="center">

![DRIVE](https://img.shields.io/badge/AI%20SSD-Guardian-00d4aa?style=for-the-badge&labelColor=0a0a0b)
![Python](https://img.shields.io/badge/Python-3.11+-3776ab?style=for-the-badge&labelColor=0a0a0b)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge&labelColor=0a0a0b)
![Build](https://img.shields.io/badge/Build-Passing-00d4aa?style=for-the-badge&labelColor=0a0a0b)

**Stop AI tools from killing your SSD.** DRIVE detects, measures, and shields.

[Get the .exe](#download) · [Demo](#how-it-works) · [Quick Start](#quick-start) · [Features](#features)

</div>

---

## The Problem

Your AI tools are silently destroying your SSD.

Running local AI agents (Claude Code, Codex CLI, Cursor, Ollama, n8n, CrewAI, AutoGen, and 20+ more) writes **15–40 GB/day** in logs, caches, and temp files to your SSD.

| Tool | Writes/Day | Risk |
|------|-----------|------|
| Codex CLI | ~640 TB/year | [Known unpatched bug #28224](https://github.com/microsoft/codex-cli/issues/28224) |
| Claude Code | ~8 GB/day | High |
| Cursor | ~5 GB/day | High |
| Ollama | ~3 GB/day | Medium |

A typical 1TB consumer SSD is rated for ~600 TBW total. At 25 GB/day, your drive has **~5–7 years max** — with heavy AI use, it can be under 2 years. There's no official fix from most of these tools.

## What DRIVE Does

1. **Scans your SSD health** — reads SMART data, translates to human terms (temperature, TBW, power-on hours, estimated life)
2. **Detects which AI tools are active** and exactly how much they're writing per day
3. **Creates a RAM-based protection shield** and redirects AI logs/caches to it — zero SSD wear
4. **Shows you real-time savings** — how much drive life you've recovered

## How It Works

```
Scan → Detect → Shield → Save
  │        │        │       │
  ▼        ▼        ▼       ▼
 SMART   AI tool   RAM    Drive life
 data    map      disk   recovered
```

The Shield works by creating a RAM disk and using NTFS junction points to redirect AI framework cache/log paths. Data stays in RAM — your SSD never sees it.

## Features

- **Real-time SSD health dashboard** — temperature, total bytes written, power-on hours, estimated remaining life
- **AI impact scan** — detects 22+ AI frameworks, estimates daily write volume per tool
- **One-click RAM Shield** — activates in seconds, redirects all AI writes to RAM
- **Before/after projection** — see exactly how much drive life DRIVE recovers for you
- **Write benchmark** — measure your actual SSD write rate over time
- **No install needed** — single .exe, no admin required to view the dashboard
- **Windows native** — uses ImDisk/PowerShell for RAM disk, no WSL required

## AI Frameworks Detected

Ollama, Claude Code, Codex CLI, Cursor, n8n, CrewAI, AutoGen, AutoGPT, ChromaDB, Weaviate, Qdrant, LM Studio, Jan, Page Assist, Continue, LocalAI, text-generation-webui, TavernAI, Vali, Mem0, GPT4All, ollama-webui.

## Quick Start

### Option 1: Run the .exe
Download from [Releases](https://github.com/diegoevillarroel/DRIVE/releases/latest) — no Python needed.

### Option 2: Run with Python
```bash
git clone https://github.com/diegoevillarroel/DRIVE.git
cd DRIVE
pip install flask pytest
python drive_main.py
```
Then open **http://localhost:8765** in your browser.

### Option 3: Build the .exe yourself
```bash
pip install pyinstaller
pyinstaller drive.spec --onefile
./dist/DRIVE.exe
```

## Architecture

```
drive_main.py    — Flask entry point (python drive_main.py)
app.py           — Web routes + API endpoints
web_ui.py        — Embedded dashboard (HTML/CSS/JS, dark theme)
models.py        — DriveInfo, FrameworkInfo, ShieldStatus, ScanResult
smart_reader.py  — SMART data via smartmontools (NVMe + SATA)
path_scanner.py  — AI framework detector (22 frameworks, cache + log paths)
shield_manager.py — RAM disk (ImDisk/PowerShell), symlink/junction redirect
config.py        — JSON config with auto-save
```

## Requirements

- Windows 10/11
- Python 3.11+ (for source) or standalone .exe
- Optional: [smartmontools](https://www.smartmontools.org/) for full SMART data (DRIVE works without it using estimated metrics)

## Testing

```bash
pytest tests/ -v
```

24 unit tests covering models, path scanning, and config.

## Contributing

Contributions welcome. Please open an issue first to discuss.

## License

MIT — use it, fork it, break it, improve it.

---

*If this saved your SSD, star the repo. It helps others find it.*