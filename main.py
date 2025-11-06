"""Command-line entry point for the spatial command platform."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Dict

from sig.core.orchestrator import SpatialCommandPlatform
from sig.config import DEFAULT_CONFIG, PlatformConfig


async def _load_events(path: Path) -> Any:
    if not path.exists():
        return []
    content = path.read_text()
    if not content.strip():
        return []
    return json.loads(content)


async def run_simulation(config: PlatformConfig, events_path: Path) -> None:
    platform = SpatialCommandPlatform(config)
    async with platform.lifecycle():
        events = await _load_events(events_path)
        for event in events:
            await platform.ingest_realtime_event(event)
        latest = platform.latest_report()
        if latest:
            print("Latest advisories:")
            for advisory in latest.advisories:
                print(" -", advisory)
        else:
            print("No advisories generated")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Spatial command platform simulator")
    parser.add_argument("events", type=Path, nargs="?", default=Path("events.json"), help="Path to events JSON file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(run_simulation(DEFAULT_CONFIG, args.events))


if __name__ == "__main__":
    main()
