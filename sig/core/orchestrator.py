"""Spatial command platform orchestrator."""
from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Deque, Dict, Iterable, Optional

from ..config import PlatformConfig, DEFAULT_CONFIG
from ..services.ai import TacticalAIService
from ..services.calculation import ParallelSpatialEngine
from ..services.data import DataFusionService
from ..services.visualization import VisualizationRelay
from .planning import OperationalPlanner


class TelemetryStream:
    """Async iterator yielding telemetry events."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._closed = asyncio.Event()

    def feed(self, event: Dict[str, Any]) -> None:
        if self._closed.is_set():
            raise RuntimeError("Telemetry stream closed")
        self._queue.put_nowait(event)

    async def close(self) -> None:
        self._closed.set()
        await self._queue.put({"type": "_stop"})

    def __aiter__(self) -> AsyncIterator[Dict[str, Any]]:
        return self._iterator()

    async def _iterator(self) -> AsyncIterator[Dict[str, Any]]:
        while True:
            item = await self._queue.get()
            if item.get("type") == "_stop":
                break
            yield item


@dataclass
class SituationReport:
    """Aggregated operational metrics."""

    generated_at: datetime
    key_metrics: Dict[str, Any] = field(default_factory=dict)
    advisories: Iterable[str] = field(default_factory=list)


class SpatialCommandPlatform:
    """High-level orchestrator connecting all tactical services."""

    def __init__(self, config: PlatformConfig = DEFAULT_CONFIG) -> None:
        self.config = config
        self.telemetry = TelemetryStream()
        self.ai_service = TacticalAIService(config)
        self.compute_engine = ParallelSpatialEngine(config)
        self.data_service = DataFusionService(config)
        self.visualization = VisualizationRelay(config)
        self.planner = OperationalPlanner(config)
        self._reports: Deque[SituationReport] = deque(maxlen=64)

    async def initialize(self) -> None:
        await asyncio.gather(
            self.ai_service.initialize(),
            self.compute_engine.initialize(),
            self.data_service.initialize(),
            self.visualization.initialize(),
        )

    async def shutdown(self) -> None:
        await asyncio.gather(
            self.visualization.shutdown(),
            self.data_service.shutdown(),
            self.compute_engine.shutdown(),
            self.ai_service.shutdown(),
        )
        await self.telemetry.close()

    async def ingest_realtime_event(self, event: Dict[str, Any]) -> None:
        self.telemetry.feed(event)
        await self.visualization.broadcast_event(event)

    async def _consume_telemetry(self) -> None:
        async for event in self.telemetry:
            await self._handle_event(event)

    async def _handle_event(self, event: Dict[str, Any]) -> None:
        terrain = await self.data_service.resolve_terrain(event)
        tasks = [
            self.compute_engine.process_terrain_analysis(terrain, event.get("parameters", {})),
            self.ai_service.assess_threat(event),
            self.planner.update_with_event(event),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        advisories = []
        for result in results:
            if isinstance(result, Exception):
                advisories.append(f"Service error: {result}")
            elif isinstance(result, dict):
                advisories.extend(result.get("advisories", []))
        report = SituationReport(generated_at=datetime.utcnow(), key_metrics={}, advisories=advisories)
        self._reports.append(report)
        await self.visualization.push_report(report)

    async def run(self) -> None:
        await self.initialize()
        try:
            await self._consume_telemetry()
        finally:
            await self.shutdown()

    def latest_report(self) -> Optional[SituationReport]:
        return self._reports[-1] if self._reports else None

    @contextlib.asynccontextmanager
    async def lifecycle(self) -> AsyncIterator["SpatialCommandPlatform"]:
        await self.initialize()
        try:
            yield self
        finally:
            await self.shutdown()
