"""
correlations.py
M8 REST: UX-02 Correlation Explorer + UX-04 Stabilization Impact view.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.orchestrator import get_orchestrator

router = APIRouter(prefix="/api/correlations", tags=["correlations"])


@router.get("")
def get_correlations():
    orch = get_orchestrator()
    cs = orch.correlations()
    return cs.model_dump(mode="json") if cs else {"items": []}


@router.get("/stabilization-impact")
def get_stabilization_impact():
    orch = get_orchestrator()
    ranking = orch.impact_ranking()
    return ranking.to_dict(orient="records") if ranking is not None else []
