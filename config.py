"""
DRIVE — AI SSD Guardian
config.py — Configuration management.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger("drive.config")


class Config:
    """
    Application configuration.
    Loaded from config.json in the DRIVE data directory,
    with environment variable overrides.
    """

    DEFAULT_CONFIG = {
        "smartmontools_path": None,  # Auto-detect from PATH
        "data_dir": None,            # Default: ~/.drive
        "ramdisk_size_gb": 4,
        "auto_activate_shield": False,
        "theme": "dark",
        "language": "en",
        "telemetry": False,          # Never send data anywhere
        "check_updates": True,
    }

    def __init__(self, data_dir: Optional[str] = None):
        # Determine data directory
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(os.environ.get("DRIVE_DATA_DIR", str(Path.home() / ".drive")))

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.data_dir / "config.json"

        # Load configuration
        self._config = self._load()

        # Override with environment variables
        if env_path := os.environ.get("SMARTMONTOOLS_PATH"):
            self._config["smartmontools_path"] = env_path

        log.info("Config loaded from %s", self.config_file)

    def _load(self) -> dict:
        """Load config file with defaults fallback."""
        config = self.DEFAULT_CONFIG.copy()

        if self.config_file.exists():
            try:
                user_config = json.loads(self.config_file.read_text())
                config.update({k: v for k, v in user_config.items() if v is not None})
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Could not load config: %s — using defaults", e)

        return config

    def save(self) -> None:
        """Persist current config to disk."""
        try:
            self.config_file.write_text(json.dumps(self._config, indent=2))
        except OSError as e:
            log.error("Could not save config: %s", e)

    def get(self, key: str, default=None):
        return self._config.get(key, default)

    def set(self, key: str, value) -> None:
        self._config[key] = value
        self.save()

    @property
    def smartmontools_path(self) -> Optional[str]:
        return self._config.get("smartmontools_path")

    @property
    def ramdisk_size_gb(self) -> int:
        return self._config.get("ramdisk_size_gb", 4)

    @property
    def telemetry(self) -> bool:
        return bool(self._config.get("telemetry", False))