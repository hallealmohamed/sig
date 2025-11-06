"""Operational planning models."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import PlatformConfig


@dataclass
class ManeuverPlan:
    """Representation of an operational maneuver."""

    identifier: str
    objectives: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    readiness: float = 0.0


class OperationalPlanner:
    """Collaborative planning service stub."""

    def __init__(self, config: PlatformConfig) -> None:
        self.config = config
        self._plans: Dict[str, ManeuverPlan] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        # Placeholder for loading plans from persistence.
        await asyncio.sleep(0)

    async def shutdown(self) -> None:
        await asyncio.sleep(0)

    async def create_plan(self, identifier: str, objectives: List[str], constraints: Dict[str, Any]) -> ManeuverPlan:
        async with self._lock:
            plan = ManeuverPlan(identifier=identifier, objectives=objectives, constraints=constraints, readiness=0.1)
            self._plans[identifier] = plan
            return plan

    async def update_with_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            for plan in self._plans.values():
                if event.get("type") == "supply_update":
                    plan.constraints["logistics"] = event.get("status", "unknown")
                    plan.readiness = min(plan.readiness + 0.05, 1.0)
                elif event.get("type") == "threat_detected":
                    plan.readiness = max(plan.readiness - 0.1, 0.0)
        return {"advisories": [f"Plans updated for event {event.get('type', 'unknown')}"]}

    async def plan_snapshot(self, identifier: str) -> Optional[ManeuverPlan]:
        async with self._lock:
            return self._plans.get(identifier)

    async def list_plans(self) -> List[ManeuverPlan]:
        async with self._lock:
            return list(self._plans.values())
