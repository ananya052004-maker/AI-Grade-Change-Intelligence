"""
feedback.py
M8 REST: FR-30/31 accept/reject with reason taxonomy; UX-05 Suggestion
Log / Feedback Quality view.
"""

from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException

from app.contracts import FeedbackResponse, RejectReason
from app.orchestrator import get_orchestrator
from app.store.feedback_store import evaluate_realised_effect, log_response, suggestion_quality_metrics

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackIn(BaseModel):
    suggestion_id: str
    response: FeedbackResponse
    operator_id: str
    reject_reason: RejectReason | None = None


@router.post("")
def submit_feedback(body: FeedbackIn):
    if body.response == FeedbackResponse.REJECTED and body.reject_reason is None:
        raise HTTPException(422, "reject_reason is required when response=REJECTED (FR-31)")
    orch = get_orchestrator()
    with orch.db_lock:  # see orchestrator.db_lock docstring: sqlite3 is not safe across threads
        log_response(orch.db, body.suggestion_id, body.response, body.operator_id, body.reject_reason)
    return {"ok": True}


class RealisedEffectIn(BaseModel):
    suggestion_id: str
    went_offspec: bool
    t_stab_s: float | None = None


@router.post("/realised-effect")
def submit_realised_effect(body: RealisedEffectIn):
    orch = get_orchestrator()
    with orch.db_lock:
        record = evaluate_realised_effect(orch.db, body.suggestion_id, body.went_offspec, body.t_stab_s,
                                           orch.risk_model.model_version)
    return record.model_dump(mode="json")


@router.get("/quality")
def quality_metrics():
    orch = get_orchestrator()
    with orch.db_lock:
        return suggestion_quality_metrics(orch.db)


@router.get("/log")
def feedback_log(limit: int = 50):
    orch = get_orchestrator()
    with orch.db_lock:
        rows = orch.db.execute(
            "SELECT * FROM suggestion_feedback ORDER BY ts_issued DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
