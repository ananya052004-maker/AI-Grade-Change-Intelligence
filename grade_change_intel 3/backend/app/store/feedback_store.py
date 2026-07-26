"""
feedback_store.py
M10: FR-30..35. Every suggestion is persisted with full inputs, model
version, and eventual outcome, immutably and append-only (FR-33). Un-
actioned suggestions auto-expire (FR-32) rather than vanishing. The realised-
effect evaluator (FR-34) is what makes M-2 (precision) meaningful at all --
E-17 requires distinguishing a genuine false alarm from "operator acted and
prevented it," and that distinction only exists if we know what actually
happened after the suggestion was issued.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from app.contracts import EvaluationRecord, FeedbackResponse, RejectReason, Suggestion
from app.store.db import append_audit_record


def log_suggestion(conn: sqlite3.Connection, suggestion: Suggestion, t_sec: float | None = None) -> None:
    """FR-33: append-only. INSERT, never UPDATE the payload/sources fields.

    t_sec: the transition's own SIMULATED replay position the suggestion was
    generated at (e.g. 440.0s into EVT0003) -- deliberately separate from
    ts_issued, which is real wall-clock time. Conflating the two is what
    produced a multi-day "seconds into this transition" figure in the Event
    Timeline; keeping them as two different fields is the actual fix.
    """
    conn.execute(
        """INSERT INTO suggestion_feedback
           (suggestion_id, ts_issued, transition_id, type, payload_json, sources_json,
            predicted_effect_json, model_version, t_sec)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            suggestion.id, suggestion.ts_issued.isoformat(), suggestion.transition_id, suggestion.type,
            json.dumps([c.model_dump() for c in suggestion.candidates], default=str),
            json.dumps([s.model_dump() for s in suggestion.sources], default=str),
            json.dumps({c.tag: c.predicted_effect for c in suggestion.candidates}, default=str),
            suggestion.model_version, t_sec,
        ),
    )
    conn.commit()
    append_audit_record(conn, datetime.now(timezone.utc).isoformat(), "SUGGESTION_ISSUED",
                         {"suggestion_id": suggestion.id, "transition_id": suggestion.transition_id})


def log_response(conn: sqlite3.Connection, suggestion_id: str, response: FeedbackResponse,
                  operator_id: str, reject_reason: RejectReason | None = None) -> None:
    """FR-30/31: accept/reject with a reason from the fixed taxonomy."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE suggestion_feedback SET ts_responded=?, response=?, operator_id=?, reject_reason=?
           WHERE suggestion_id=?""",
        (now, response.value, operator_id, reject_reason.value if reject_reason else None, suggestion_id),
    )
    conn.commit()
    append_audit_record(conn, now, "SUGGESTION_RESPONSE",
                         {"suggestion_id": suggestion_id, "response": response.value, "operator_id": operator_id})


def mark_superseded(conn: sqlite3.Connection, suggestion_id: str) -> None:
    """FR-16: a superseded suggestion is marked, not silently dropped."""
    log_response(conn, suggestion_id, FeedbackResponse.SUPERSEDED, operator_id="SYSTEM")


def expire_stale_suggestions(conn: sqlite3.Connection, now: datetime, ttl_s: int) -> list[str]:
    """FR-32: un-actioned suggestions MUST auto-expire, never silently
    discarded -- this writes an explicit EXPIRED response, not a delete."""
    rows = conn.execute(
        "SELECT suggestion_id, ts_issued FROM suggestion_feedback WHERE response IS NULL"
    ).fetchall()
    expired = []
    for row in rows:
        issued = datetime.fromisoformat(row["ts_issued"])
        if (now - issued).total_seconds() > ttl_s:
            log_response(conn, row["suggestion_id"], FeedbackResponse.EXPIRED, operator_id="SYSTEM")
            expired.append(row["suggestion_id"])
    return expired


def evaluate_realised_effect(conn: sqlite3.Connection, suggestion_id: str, went_offspec: bool,
                              t_stab_s: float | None, model_version: str) -> EvaluationRecord:
    """FR-34/E-17: classify what actually happened, distinguishing a real
    false alarm from a prevented excursion."""
    row = conn.execute("SELECT * FROM suggestion_feedback WHERE suggestion_id=?", (suggestion_id,)).fetchone()
    response = row["response"] if row else None

    if response == FeedbackResponse.ACCEPTED.value and not went_offspec:
        classification = "TRUE_POSITIVE_PREVENTED"
    elif response == FeedbackResponse.ACCEPTED.value and went_offspec:
        classification = "ACCEPTED_BUT_STILL_OFFSPEC"
    elif response == FeedbackResponse.REJECTED.value and went_offspec:
        classification = "MISS_REJECTED"
    elif response in (None, FeedbackResponse.EXPIRED.value) and went_offspec:
        classification = "MISS_UNACTIONED"
    elif not went_offspec:
        classification = "FALSE_ALARM" if response != FeedbackResponse.ACCEPTED.value else "TRUE_POSITIVE_PREVENTED"
    else:
        classification = "UNKNOWN"

    record = EvaluationRecord(
        suggestion_id=suggestion_id, transition_id=row["transition_id"] if row else "",
        went_offspec=went_offspec, t_stab_s=t_stab_s, classification=classification, model_version=model_version,
    )
    conn.execute(
        "UPDATE suggestion_feedback SET realised_effect_json=? WHERE suggestion_id=?",
        (json.dumps(record.model_dump(), default=str), suggestion_id),
    )
    conn.commit()
    return record


def suggestion_quality_metrics(conn: sqlite3.Connection) -> dict:
    """UX-05 / FR-35: acceptance rate + rolling precision/recall, by model
    version and suggestion type, for the Suggestion Log / Feedback Quality view."""
    rows = conn.execute("SELECT * FROM suggestion_feedback").fetchall()
    total = len(rows)
    if total == 0:
        return {"total": 0, "acceptance_rate": None, "by_model_version": {}}

    accepted = sum(1 for r in rows if r["response"] == FeedbackResponse.ACCEPTED.value)
    expired = sum(1 for r in rows if r["response"] == FeedbackResponse.EXPIRED.value)
    rejected = sum(1 for r in rows if r["response"] == FeedbackResponse.REJECTED.value)

    by_version: dict[str, dict] = {}
    for r in rows:
        v = r["model_version"]
        by_version.setdefault(v, {"total": 0, "accepted": 0})
        by_version[v]["total"] += 1
        if r["response"] == FeedbackResponse.ACCEPTED.value:
            by_version[v]["accepted"] += 1
    for v, d in by_version.items():
        d["acceptance_rate"] = d["accepted"] / d["total"] if d["total"] else None

    return {
        "total": total, "accepted": accepted, "rejected": rejected, "expired": expired,
        "acceptance_rate": accepted / total, "by_model_version": by_version,
    }
