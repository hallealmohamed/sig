"""Configuration models for the next-generation GIS platform."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(slots=True)
class DatabaseConfig:
    """Connection parameters for the spatial data stores."""

    postgis_dsn: str = "postgresql://gis:gis@localhost:5432/battlemap"
    rasdaman_url: str = "http://localhost:7000/rasdaman"
    redis_url: str = "redis://localhost:6379/0"
    elastic_url: str = "http://localhost:9200"


@dataclass(slots=True)
class StreamingConfig:
    """Messaging configuration for real-time data feeds."""

    kafka_bootstrap: str = "localhost:9092"
    topics: List[str] = field(default_factory=lambda: ["telemetry", "intel", "alerts"])


@dataclass(slots=True)
class ComputeConfig:
    """Tuning parameters for the parallel computation backends."""

    enable_gpu: bool = False
    max_workers: int = 8
    dask_scheduler: Optional[str] = None
    cache_directory: Path = Path(".cache/spatial")


@dataclass(slots=True)
class ThemeConfig:
    """UI theme defaults."""

    default_theme: str = "tactical_day"
    available_themes: Dict[str, Dict[str, str]] = field(
        default_factory=lambda: {
            "tactical_day": {"background": "#0b1d2a", "foreground": "#d7e7ff"},
            "tactical_night": {"background": "#05090f", "foreground": "#7ad1ff"},
            "infrared": {"background": "#2a0000", "foreground": "#ffb347"},
        }
    )


@dataclass(slots=True)
class PlatformConfig:
    """High-level configuration aggregator."""

    databases: DatabaseConfig = field(default_factory=DatabaseConfig)
    streaming: StreamingConfig = field(default_factory=StreamingConfig)
    compute: ComputeConfig = field(default_factory=ComputeConfig)
    theme: ThemeConfig = field(default_factory=ThemeConfig)


DEFAULT_CONFIG = PlatformConfig()
