"""
ws.py
M8 WebSocket: pushes a tick snapshot every prediction cycle (Appendix B
predict.cycle_s=5s) at a wall-clock pace scaled by `speed`, so a demo can
watch risk state evolve live without waiting the full transition duration.
UX-10: the live view must update within 2s of a new prediction cycle --
at the default speed this websocket pushes far faster than that ceiling.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.jsonsafe import sanitize
from app.orchestrator import get_orchestrator

router = APIRouter()


@router.websocket("/ws/transitions/{event_id}")
async def stream_transition(websocket: WebSocket, event_id: str, speed: float = 20.0):
    await websocket.accept()
    orch = get_orchestrator()
    if orch.ge[orch.ge["transition_id"] == event_id].empty:
        await websocket.send_json({"error": f"unknown transition_id {event_id}"})
        await websocket.close()
        return

    wide = orch.wide_for(event_id)
    cycle_s = orch.settings.predict.cycle_s
    delay = cycle_s / speed

    try:
        for t_sec in wide["t_sec"].values:
            snapshot = orch.tick(event_id, float(t_sec))
            await websocket.send_json(sanitize(snapshot))
            await asyncio.sleep(delay)
        await websocket.send_json({"done": True})
    except WebSocketDisconnect:
        return
