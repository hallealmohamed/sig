"""FastAPI gateway exposing orchestrator capabilities."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from ..config import DEFAULT_CONFIG
from ..core.orchestrator import SpatialCommandPlatform
from ..core.planning import ManeuverPlan

app = FastAPI(title="SIG Command Gateway", version="0.1.0")
platform = SpatialCommandPlatform(DEFAULT_CONFIG)


@app.on_event("startup")
async def startup_event() -> None:
    await platform.initialize()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await platform.shutdown()


@app.post("/plans/{identifier}")
async def create_plan(identifier: str, payload: Dict[str, Any]) -> ManeuverPlan:
    objectives = payload.get("objectives", [])
    constraints = payload.get("constraints", {})
    return await platform.planner.create_plan(identifier, objectives, constraints)


@app.post("/events")
async def push_event(payload: Dict[str, Any]) -> Dict[str, str]:
    await platform.ingest_realtime_event(payload)
    return {"status": "queued"}


@app.websocket("/ws/sitreps")
async def sitrep_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = await platform.visualization.register()
    try:
        while True:
            report = await queue.get()
            await websocket.send_json(report)
    except WebSocketDisconnect:
        pass


@app.get("/reports/latest")
async def latest_report() -> Dict[str, Any]:
    report = platform.latest_report()
    if report is None:
        return {"generated_at": None, "advisories": []}
    return {"generated_at": report.generated_at.isoformat(), "advisories": list(report.advisories)}
