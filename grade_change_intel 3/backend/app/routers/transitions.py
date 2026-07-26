"""
transitions.py
M8 REST: transition listing + per-cycle snapshot (UX-01 Live Transition view).
"""

from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException

from app.orchestrator import get_orchestrator

router = APIRouter(prefix="/api/transitions", tags=["transitions"])


@router.get("")
def list_transitions():
    orch = get_orchestrator()
    return orch.list_events()


@router.get("/{event_id}")
def get_transition(event_id: str):
    orch = get_orchestrator()
    rows = orch.ge[orch.ge["transition_id"] == event_id]
    if rows.empty:
        raise HTTPException(404, f"unknown transition_id {event_id}")
    ev = rows.iloc[0]
    wide = orch.wide_for(event_id)
    return {
        "transition_id": event_id, "grade_from": ev["grade_from"], "grade_to": ev["grade_to"],
        "outcome": ev["outcome"], "fault_injected": ev["fault_injected"],
        "stabilization_time_sec": ev["stabilization_time_sec"], "chained": bool(ev["chained"]),
        "confounded": bool(ev["confounded"]), "max_t_sec": float(wide["t_sec"].max()),
        "final_target_bw": float(orch.grade_targets[ev["grade_to"]]),
    }


@router.get("/{event_id}/history")
def history(event_id: str):
    orch = get_orchestrator()
    if orch.ge[orch.ge["transition_id"] == event_id].empty:
        raise HTTPException(404, f"unknown transition_id {event_id}")
    return orch.history(event_id)


@router.get("/{event_id}/tick")
def tick(event_id: str, t_sec: float):
    orch = get_orchestrator()
    if orch.ge[orch.ge["transition_id"] == event_id].empty:
        raise HTTPException(404, f"unknown transition_id {event_id}")
    snapshot = orch.tick(event_id, t_sec)
    if "error" in snapshot:
        raise HTTPException(400, snapshot["error"])
    return snapshot


@router.get("/{event_id}/timeline")
def timeline(event_id: str):
    orch = get_orchestrator()
    if orch.ge[orch.ge["transition_id"] == event_id].empty:
        raise HTTPException(404, f"unknown transition_id {event_id}")
    return orch.event_timeline(event_id)


class WhatIfIn(BaseModel):
    t_sec: float
    overrides: dict[str, float]


@router.post("/{event_id}/whatif")
def whatif(event_id: str, body: WhatIfIn):
    orch = get_orchestrator()
    if orch.ge[orch.ge["transition_id"] == event_id].empty:
        raise HTTPException(404, f"unknown transition_id {event_id}")
    result = orch.whatif(event_id, body.t_sec, body.overrides)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/{event_id}/drop_tag/{canonical_tag}")
def drop_tag(event_id: str, canonical_tag: str):
    """AC-13: demonstrate the System degrades correctly when a primary tag
    is removed at runtime."""
    orch = get_orchestrator()
    orch.adapter.drop_tag(canonical_tag)
    return {"dropped": canonical_tag}


@router.post("/{event_id}/restore_tag/{canonical_tag}")
def restore_tag(event_id: str, canonical_tag: str):
    orch = get_orchestrator()
    orch.adapter.restore_tag(canonical_tag)
    return {"restored": canonical_tag}
