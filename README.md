# DRIVE — AI SSD Guardian

Your AI tools are silently destroying your SSD. DRIVE shows you the damage and stops it.

## The Problem

Running local AI agents (Claude Code, Codex CLI, Cursor, Ollama, n8n, CrewAI, etc.) writes
15-40 GB/day in logs, caches, and temp files to your SSD. A typical 1TB consumer SSD is
rated for ~600 TBW total. At 25 GB/day, that's ~9 TB/year — your drive has ~5-7 years max.
With heavy AI use, it can be under 2 years.

OpenAI Codex CLI alone writes 640 TB/year due to an unpatched bug (GitHub Issue #28224,
reported June 2026). There's no official fix.

## What DRIVE Does

1. **Scans your SSD health** — reads SMART data, translates to human terms
2. **Detects which AI tools are active** and how much they're writing per day
3. **Creates a RAM-based protection layer** and redirects AI logs/caches to it
4. **Shows you exactly how much drive life you've saved** — real-time dashboard

## Quick Start

```bash
# Run directly
python drive.py

# Build .exe (requires PyInstaller)
pyinstaller drive.spec --onefile
./dist/drive.exe
```

Then open http://localhost:8765 in your browser.

## Architecture

- `drive.py` — Flask server + web UI (HTML/JS/CSS embedded)
- `smart_reader.py` — smartmontools integration for Windows
- `ramdisk_manager.py` — Windows RAMDisk creation via WinAPI
- `path_scanner.py` — detects AI frameworks and their data paths
- `shield_manager.py` — symlink redirection engine
- `models.py` — data models (DriveInfo, FrameworkInfo, ShieldStatus)
- `config.py` — configuration loader

## AI Frameworks Detected

Ollama, Claude Code, Codex CLI, Cursor, n8n, CrewAI, AutoGen, AutoGPT,
ChromaDB, Weaviate, Qdrant, LM Studio, Jan, Page Assist, Continue,
ollama-webui, localai, vali, mem0, text-generation-webui, TavernAI,
and more.

## Requirements

- Windows 10/11 (64-bit)
- Python 3.11+
- smartmontools (auto-bundled or system-installed)
- Admin privileges for RAMDisk and symlink creation

## License

MIT — The SSD protection is free. Your data never leaves your machine.

## Website

getdrive.io