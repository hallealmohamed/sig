"""Visualization relay for dashboards and clients."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from ..config import PlatformConfig
from ..core.color import IntelligentColorEngine, LayerDescriptor


class VisualizationRelay:
    """Fan-out layer for broadcasting events to dashboards and tactical views."""

    def __init__(self, config: PlatformConfig) -> None:
        self.config = config
        self._subscribers: List[asyncio.Queue] = []
        self._color_engine = IntelligentColorEngine()

    async def initialize(self) -> None:
        await asyncio.sleep(0)

    async def shutdown(self) -> None:
        for queue in self._subscribers:
            queue.put_nowait({"type": "shutdown"})
        self._subscribers.clear()

    async def register(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=128)
        self._subscribers.append(queue)
        return queue

    async def broadcast_event(self, event: Dict[str, Any]) -> None:
        for queue in self._subscribers:
            await queue.put(event)

    async def push_report(self, report: Any) -> None:
        payload = {"type": "sitreps", "data": report.advisories}
        for queue in self._subscribers:
            await queue.put(payload)

    def colorize_layers(self, layers: List[LayerDescriptor], context: str) -> Dict[str, str]:
        return self._color_engine.assign_optimal_colors(layers, context=context)
