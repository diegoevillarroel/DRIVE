"""
DRIVE — AI SSD Guardian
path_scanner.py — Detects AI frameworks installed on the system and their data paths.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import List, Optional

from models import FrameworkInfo

log = logging.getLogger("drive.scanner")


# ─── AI Framework Registry ────────────────────────────────────────────────────
# Maps framework IDs to their detection patterns and metadata.
# Each entry: (name, search_paths_template, cache_patterns, log_patterns, is_running_indicator)

AI_FRAMEWORKS: List[dict] = [
    {
        "id": "ollama",
        "name": "Ollama",
        "website": "https://ollama.com",
        "search_paths": [
            "~/.ollama",
            "%USERPROFILE%\\.ollama",
        ],
        "cache_patterns": ["models/", "manifests/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": "ollama.exe",
    },
    {
        "id": "claude_code",
        "name": "Claude Code",
        "website": "https://claude.com/code",
        "search_paths": [
            "~/.claude",
            "%USERPROFILE%\\.claude",
        ],
        "cache_patterns": ["projects/", "memory/"],
        "log_patterns": ["logs/", ".claude/hooks/"],
        "is_running_indicator": "claude.exe",
    },
    {
        "id": "codex",
        "name": "OpenAI Codex CLI",
        "website": "https://github.com/openai/codex",
        "search_paths": [
            "~/.codex",
            "%USERPROFILE%\\.codex",
        ],
        "cache_patterns": ["hooks/", "projects/"],
        "log_patterns": ["logs/", "logs_2.sqlite"],
        "is_running_indicator": "codex.exe",
    },
    {
        "id": "cursor",
        "name": "Cursor AI",
        "website": "https://cursor.com",
        "search_paths": [
            "%APPDATA\\Cursor",
            "%LOCALAPPDATA\\Cursor",
            "~/.cursor",
        ],
        "cache_patterns": ["Cache/", "GPUCache/", "logs/"],
        "log_patterns": ["logs/", "crashpad/"],
        "is_running_indicator": "cursor.exe",
    },
    {
        "id": "n8n",
        "name": "n8n Workflow",
        "website": "https://n8n.io",
        "search_paths": [
            "~/.n8n",
            "%USERPROFILE%\\.n8n",
            "%APPDATA\\n8n",
        ],
        "cache_patterns": ["database/"],
        "log_patterns": ["logs/", ".n8n/"],
        "is_running_indicator": "n8n.exe",
    },
    {
        "id": "crewai",
        "name": "CrewAI",
        "website": "https://crewai.com",
        "search_paths": [
            "~/.crewai",
            ".crewai/",
        ],
        "cache_patterns": ["logs/", "cache/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": None,
    },
    {
        "id": "autogen",
        "name": "AutoGen",
        "website": "https://microsoft.github.io/autogen",
        "search_paths": [
            "~/.autogen",
        ],
        "cache_patterns": ["cache/", "logs/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": None,
    },
    {
        "id": "autogpt",
        "name": "AutoGPT",
        "website": "https://agentgpt.reworkd.ai",
        "search_paths": [
            "~/.autogpt",
        ],
        "cache_patterns": ["data/", "logs/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": "autogpt",
    },
    {
        "id": "chroma",
        "name": "ChromaDB",
        "website": "https://trychroma.com",
        "search_paths": [
            "~/.chroma",
        ],
        "cache_patterns": ["persist/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": "chroma",
    },
    {
        "id": "weaviate",
        "name": "Weaviate",
        "website": "https://weaviate.io",
        "search_paths": [
            "~/weaviate_data",
        ],
        "cache_patterns": ["data/", "backup/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": "weaviate",
    },
    {
        "id": "qdrant",
        "name": "Qdrant",
        "website": "https://qdrant.tech",
        "search_paths": [
            "~/qdrant_storage",
        ],
        "cache_patterns": ["storage/", "backup/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": "qdrant",
    },
    {
        "id": "lm_studio",
        "name": "LM Studio",
        "website": "https://lmstudio.ai",
        "search_paths": [
            "%APPDATA\\LM Studio",
            "%LOCALAPPDATA\\LM Studio",
        ],
        "cache_patterns": ["models/", "cache/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": "LM Studio.exe",
    },
    {
        "id": "jan",
        "name": "Jan",
        "website": "https://jan.ai",
        "search_paths": [
            "~/.jan",
            "%APPDATA\\Jan",
        ],
        "cache_patterns": ["models/", "extensions/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": "jan.exe",
    },
    {
        "id": "page_assist",
        "name": "Page Assist",
        "website": "https://github.com/n4ze3m/page-assist",
        "search_paths": [
            "%APPDATA\\page-assist",
            "%LOCALAPPDATA\\page-assist",
        ],
        "cache_patterns": ["models/", "cache/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": "page-assist",
    },
    {
        "id": "continue",
        "name": "Continue",
        "website": "https://continue.dev",
        "search_paths": [
            "~/.continue",
            "%USERPROFILE%\\.continue",
        ],
        "cache_patterns": ["cache/", "models/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": "continue",
    },
    {
        "id": "localai",
        "name": "LocalAI",
        "website": "https://localai.io",
        "search_paths": [
            "~/.localai",
            "/tmp/localai",
        ],
        "cache_patterns": ["models/", "backup/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": "localai",
    },
    {
        "id": "text_generation_webui",
        "name": "text-generation-webui",
        "website": "https://github.com/oobabooga/text-generation-webui",
        "search_paths": [
            "~/text-generation-webui",
            "~/oobabooga_text_generation_webui",
        ],
        "cache_patterns": ["models/", "loras/", "textgen_settings/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": None,
    },
    {
        "id": "gpt4all",
        "name": "GPT4All",
        "website": "https://gpt4all.io",
        "search_paths": [
            "%LOCALAPPDATA\\GPT4All",
            "%APPDATA\\GPT4All",
        ],
        "cache_patterns": ["models/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": "gpt4all",
    },
    {
        "id": "vali",
        "name": "Vali",
        "website": "https://github.com/vali-dev/vali",
        "search_paths": [
            "~/.vali",
            "%USERPROFILE%\\.vali",
        ],
        "cache_patterns": ["cache/", "memory/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": "vali",
    },
    {
        "id": "mem0",
        "name": "Mem0",
        "website": "https://mem0.ai",
        "search_paths": [
            "~/.mem0",
        ],
        "cache_patterns": ["memory/", "graphs/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": None,
    },
    {
        "id": "ollama_webui",
        "name": "Ollama WebUI",
        "website": "https://github.com/ollama-webui/ollama-webui",
        "search_paths": [
            "~/ollama-webui",
            "/app/ollama-webui",
        ],
        "cache_patterns": ["locales/", ".ollama-webui/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": None,
    },
    {
        "id": " TavernAI",
        "name": "TavernAI",
        "website": "https://github.com/TavernAI/TavernAI",
        "search_paths": [
            "~/TavernAI",
        ],
        "cache_patterns": ["characters/", "chats/"],
        "log_patterns": ["logs/"],
        "is_running_indicator": None,
    },
]


def _expand_path(path: str) -> Optional[Path]:
    """Expand environment variables and ~ in a path string."""
    expanded = os.path.expandvars(os.path.expanduser(path))
    try:
        return Path(expanded)
    except Exception:
        return None


def _is_running(process_indicator: Optional[str]) -> bool:
    """Check if a process is currently running."""
    if not process_indicator:
        return False

    try:
        import subprocess
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_indicator}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return process_indicator.lower() in result.stdout.lower()
    except Exception:
        return False


class PathScanner:
    """
    Scans the filesystem for installed AI frameworks and their data directories.
    Returns a list of detected FrameworkInfo objects.
    """

    def __init__(self):
        self._cache: List[FrameworkInfo] = []
        self._cache_valid = False

    def scan_all(self, force: bool = False) -> List[FrameworkInfo]:
        """
        Scan all known AI framework paths.
        Results are cached for the lifetime of the scanner instance.
        """
        if self._cache_valid and not force:
            return self._cache

        detected = []

        for fw in AI_FRAMEWORKS:
            info = self._detect_framework(fw)
            if info is not None:
                # Only add if at least one path exists
                if info.cache_paths or info.log_paths or info.detected_path:
                    info.is_running = _is_running(fw.get("is_running_indicator"))
                    info.estimate_daily_writes()
                    detected.append(info)

        self._cache = detected
        self._cache_valid = True
        return detected

    def _detect_framework(self, fw: dict) -> Optional[FrameworkInfo]:
        """Detect a single framework's presence and paths."""
        cache_paths: List[str] = []
        log_paths: List[str] = []
        detected_root: Optional[str] = None

        for raw_path in fw.get("search_paths", []):
            root = _expand_path(raw_path)
            if root is None:
                continue

            try:
                if not root.exists():
                    continue
            except PermissionError:
                log.debug("Permission denied: %s", root)
                continue
            except OSError as e:
                log.debug("Cannot access %s: %s", root, e)
                continue

            detected_root = str(root)

            # Scan for cache paths
            for pattern in fw.get("cache_patterns", []):
                candidate = root / pattern.rstrip("/")
                try:
                    if candidate.exists():
                        cache_paths.append(str(candidate))
                except (OSError, PermissionError):
                    pass

            # Scan for log paths
            for pattern in fw.get("log_patterns", []):
                candidate = root / pattern.rstrip("/")
                try:
                    if candidate.exists():
                        log_paths.append(str(candidate))
                except (OSError, PermissionError):
                    pass

            # Also check for the framework's own log/database files
            if not cache_paths and not log_paths:
                # Check root directory contents
                try:
                    for item in root.iterdir():
                        name = item.name.lower()
                        if any(kw in name for kw in ["log", "cache", "data", "db", "sqlite"]):
                            if item.is_dir():
                                log_paths.append(str(item))
                            elif item.is_file():
                                cache_paths.append(str(item.parent))
                except (OSError, PermissionError):
                    pass

        if not detected_root:
            return None

        return FrameworkInfo(
            id=fw["id"],
            name=fw["name"],
            detected_path=detected_root,
            cache_paths=cache_paths,
            log_paths=log_paths,
            config_path=detected_root,
            website=fw.get("website", ""),
        )

    def get_frameworks_by_severity(self, min_gb: float = 2.0) -> dict:
        """Group detected frameworks by write severity."""
        all_fw = self.scan_all()
        return {
            "high": [f for f in all_fw if f.estimated_daily_gb >= 10],
            "medium": [f for f in all_fw if 2 <= f.estimated_daily_gb < 10],
            "low": [f for f in all_fw if f.estimated_daily_gb < 2],
        }