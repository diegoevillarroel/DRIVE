# DRIVE — AI SSD Guardian

## Installation

```bash
pip install -r requirements.txt
python drive_main.py
```

Then open http://localhost:8765

## Build executable

```bash
pip install pyinstaller
pyinstaller drive.spec --onefile
./dist/DRIVE.exe
```

## Run tests

```bash
pip install pytest
pytest tests/ -v
```

## Supported AI Frameworks

- Ollama
- Claude Code
- OpenAI Codex CLI (known to write 640 TB/year unpatched)
- Cursor
- n8n
- CrewAI
- AutoGen / AutoGPT
- ChromaDB / Weaviate / Qdrant
- LM Studio / Jan / Page Assist
- Continue / text-generation-webui
- and more

## Architecture

```
drive/
  drive_main.py      — entry point
  __init__.py         — Flask app factory
  web_ui.py           — embedded HTML/CSS/JS dashboard
  models.py           — data models
  smart_reader.py     — SMART data via smartmontools
  path_scanner.py     — AI framework detection
  shield_manager.py   — RAM disk + symlink redirection
  config.py           — configuration
  tests/              — pytest suite
  .github/workflows/  — CI/CD
```

## License

MIT — your data never leaves your machine.