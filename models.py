"""
DRIVE — AI SSD Guardian
Data models for type safety and serialization.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional, List


class AppState(dict):
    """In-memory app state shared across requests. Keys: shield_active, last_scan, last_scan_time, ramdisk_letter."""
    pass


@dataclass
class DriveInfo:
    """SSD/HDD health information from SMART data."""
    model: Optional[str] = None
    serial: Optional[str] = None
    capacity_gb: Optional[float] = None
    health_percent: Optional[float] = None  # 0-100
    temperature_c: Optional[int] = None
    power_on_hours: Optional[int] = None
    power_cycles: Optional[int] = None
    tbw_written_tb: Optional[float] = None  # Terabytes Written
    tbw_rated_tb: Optional[float] = None    # Rated TBW (from spec)
    spare_remaining_pct: Optional[int] = None  # Spare block remaining
    wear_leveling: Optional[int] = None     # Wear leveling count
    interface: Optional[str] = None         # NVMe, SATA, etc.
    firmware: Optional[str] = None
    projected_life_months: Optional[float] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # Round floats for cleaner JSON
        for k, v in d.items():
            if isinstance(v, float):
                d[k] = round(v, 3)
        return d

    def estimate_life_months(self, daily_gb: float) -> Optional[float]:
        """
        Estimate remaining life in months given average daily writes.
        Uses the TBW metric if available, otherwise returns None.
        """
        if self.tbw_written_tb is None or daily_gb <= 0:
            return None

        daily_tb = daily_gb / 1024.0
        if self.tbw_rated_tb:
            remaining_tb = self.tbw_rated_tb - self.tbw_written_tb
            if remaining_tb <= 0:
                return 0.0
            return round(remaining_tb / daily_tb / 30.0, 1)
        else:
            # Fallback: assume ~600 TBW rated (common consumer SSD)
            rated = self.tbw_rated_tb or 600.0
            remaining_tb = rated - self.tbw_written_tb
            if remaining_tb <= 0:
                return 0.0
            return round(remaining_tb / daily_tb / 30.0, 1)


@dataclass
class FrameworkInfo:
    """Detected AI framework with write estimates."""
    id: str
    name: str
    detected_path: Optional[str] = None
    cache_paths: List[str] = field(default_factory=list)
    log_paths: List[str] = field(default_factory=list)
    config_path: Optional[str] = None
    is_running: bool = False
    estimated_daily_gb: float = 0.0
    severity: str = "low"  # low, medium, high
    website: str = ""

    def estimate_daily_writes(self) -> float:
        """
        Estimate daily GB written based on known usage patterns.
        These are conservative estimates based on typical AI workflow data.
        """
        if not self.is_running:
            self.estimated_daily_gb = 0.0
            self.severity = "low"
            return 0.0

        # GB/day estimates based on typical AI agent usage patterns
        estimates = {
            "ollama": 3.0,
            "claude_code": 8.0,
            "codex": 15.0,  # Codex CLI has the known bug
            "cursor": 5.0,
            "n8n": 4.0,
            "crewai": 3.0,
            "autogen": 3.0,
            "autogpt": 3.0,
            "chroma": 5.0,
            "weaviate": 3.0,
            "qdrant": 3.0,
            "lm_studio": 4.0,
            "jan": 3.0,
            "page_assist": 2.0,
            "continue": 2.0,
            "localai": 3.0,
            "text_generation_webui": 5.0,
            " TavernAI": 1.0,
            "vali": 2.0,
            "mem0": 4.0,
            "gpt4all": 3.0,
            "ollama_webui": 2.0,
        }

        key = self.id.lower()
        base = estimates.get(key, 2.0)

        # Factor in number of paths present
        path_factor = 1.0 + (len(self.cache_paths) + len(self.log_paths)) * 0.1
        base *= min(path_factor, 2.0)

        self.estimated_daily_gb = round(base, 2)
        self.severity = (
            "high" if self.estimated_daily_gb >= 10
            else "medium" if self.estimated_daily_gb >= 2
            else "low"
        )
        return self.estimated_daily_gb

    def to_dict(self) -> dict:
        d = asdict(self)
        d["estimated_daily_gb"] = round(self.estimated_daily_gb, 3)
        return d


@dataclass
class ShieldStatus:
    """Current state of the SSD protection shield."""
    active: bool = False
    ramdisk_letter: Optional[str] = None
    ramdisk_size_gb: int = 0
    redirected_count: int = 0
    estimated_ssd_savings_gb_per_day: float = 0.0
    activated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanResult:
    """Complete scan result combining drive health + AI impact."""
    drive: DriveInfo
    frameworks: List[dict]  # List[FrameworkInfo.to_dict()]
    total_daily_gb: float
    shield_active: bool
    scan_duration_ms: int
    projected_life_months: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "drive": self.drive.to_dict() if isinstance(self.drive, DriveInfo) else self.drive,
            "frameworks": self.frameworks,
            "total_daily_gb": round(self.total_daily_gb, 3),
            "shield_active": self.shield_active,
            "scan_duration_ms": self.scan_duration_ms,
            "projected_life_months": self.projected_life_months,
        }