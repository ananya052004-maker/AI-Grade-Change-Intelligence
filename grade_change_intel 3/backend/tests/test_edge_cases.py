"""
Sec 11 named edge cases -- the subset prioritized for automated coverage in
this build (NFR-13). Each test is named after its edge-case ID so a failure
points straight back to the PRD row.
"""

from datetime import datetime, timezone

import pandas as pd
import pytest

from app.contracts import FeedbackResponse, Quality, RiskState
from app.ingestion.tag_registry import get_tag_registry
from app.ingestion.validation import IngestionValidator
from app.knowledge.recipe_limits import RecipeLimitsStore
from app.recommend.optimizer import redirect_saturated_handles
from app.store.db import get_connection
from app.store.feedback_store import evaluate_realised_effect, log_response, log_suggestion


# ---------------------------------------------------------------- E-05
def test_E05_unit_mismatch_detected_at_registry_level():
    registry = get_tag_registry()
    assert registry.validate_unit("BW_MEAS", "gsm") is True
    assert registry.validate_unit("BW_MEAS", "lb/3000ft2") is False, "unit mismatch must be detectable, not a runtime surprise"


# ---------------------------------------------------------------- E-07
def test_E07_missing_recipe_entry_for_target_grade():
    store = RecipeLimitsStore()
    assert store.has_grade("GradeA") is True
    assert store.has_grade("GradeZ_DOES_NOT_EXIST") is False


# ---------------------------------------------------------------- E-08
def test_E08_sheet_break_events_are_aborted_and_excluded_from_success(trained_orchestrator):
    aborted = trained_orchestrator.ge[trained_orchestrator.ge["fault_injected"] == "sheet_break"]
    assert len(aborted) > 0, "test dataset should contain at least one sheet_break-faulted transition"
    assert (aborted["outcome"] == "ABORTED").all()


# ---------------------------------------------------------------- E-11
def test_E11_saturated_handle_is_redirected_not_recommended():
    ranked = ["STEAM_PRESS_G1", "STOCK_FLOW", "MACHINE_SPEED"]
    saturation = {"STEAM_PRESS_G1": True, "STOCK_FLOW": False, "MACHINE_SPEED": False}
    usable, saturated = redirect_saturated_handles(ranked, saturation)
    assert "STEAM_PRESS_G1" not in usable
    assert "STEAM_PRESS_G1" in saturated
    assert usable == ["STOCK_FLOW", "MACHINE_SPEED"]


# ---------------------------------------------------------------- E-13
def test_E13_unseen_grade_pair_triggers_low_confidence(trained_orchestrator):
    from app.features.feature_engine import feature_columns

    ev = trained_orchestrator.ge.iloc[0]
    wide = trained_orchestrator.wide_for(ev["transition_id"])
    row = wide.iloc[len(wide) // 2]
    feats = {c: row[c] for c in feature_columns() if c in row.index and pd.notna(row[c])}

    risk = trained_orchestrator.risk_model.predict(feats, "GradeA", "GradeA")  # never a real transition
    assert risk.state == RiskState.LOW_CONFIDENCE


# ---------------------------------------------------------------- E-17
def test_E17_false_alarm_distinguished_from_prevented_excursion(tmp_path):
    conn = get_connection(db_path=tmp_path / "test_e17.db")
    from app.contracts import CandidateSuggestion, Source, SourceType, Suggestion
    from datetime import timedelta

    def make_suggestion(sid):
        return Suggestion(
            id=sid, transition_id="EVT_E17", ts_issued=datetime.now(timezone.utc), type="setpoint_recommendation",
            candidates=[CandidateSuggestion(tag="STOCK_FLOW", from_value=100, to_value=101, ramp_rate=0.2,
                                             predicted_effect={}, feasible=True)],
            sources=[Source(type=SourceType.HISTORICAL_ANALOG, reference="test", weight=0.5, confidence=0.5)],
            rationale_text="test", confidence=0.5, model_version="test",
            ttl_s=300, expires_at=datetime.now(timezone.utc) + timedelta(seconds=300),
        )

    log_suggestion(conn, make_suggestion("SUG-E17-ACCEPTED"))
    log_response(conn, "SUG-E17-ACCEPTED", FeedbackResponse.ACCEPTED, "OP01")
    prevented = evaluate_realised_effect(conn, "SUG-E17-ACCEPTED", went_offspec=False, t_stab_s=100, model_version="test")
    assert prevented.classification == "TRUE_POSITIVE_PREVENTED"

    log_suggestion(conn, make_suggestion("SUG-E17-REJECTED"))
    log_response(conn, "SUG-E17-REJECTED", FeedbackResponse.REJECTED, "OP01", None)
    missed = evaluate_realised_effect(conn, "SUG-E17-REJECTED", went_offspec=True, t_stab_s=None, model_version="test")
    assert missed.classification == "MISS_REJECTED", "a rejected suggestion that DID go off-spec is not a false alarm"


# ---------------------------------------------------------------- E-21
def test_E21_stale_data_penalises_confidence_not_silently_ignored():
    validator = IngestionValidator()
    registry = get_tag_registry()
    from app.contracts import Frame, TagSample

    good_tags = {t: TagSample(value=50.0, quality=Quality.GOOD) for t in registry.all_canonical()}
    good_frame = Frame(ts=datetime.now(timezone.utc), machine_id="PM1", tags=good_tags)
    validator.validate(good_frame)  # establish last-known-good

    stale_tags = dict(good_tags)
    stale_tags["BW_MEAS"] = TagSample(value=50.0, quality=Quality.BAD)
    for _ in range(5):  # exceed max_forward_fill_scans
        _, report = validator.validate(Frame(ts=datetime.now(timezone.utc), machine_id="PM1", tags=stale_tags))
    assert "BW_MEAS" in report.stale_tags
    assert report.confidence_penalty > 0


# ---------------------------------------------------------------- E-28
def test_E28_cold_start_no_history_returns_explicit_reason(trained_orchestrator):
    from app.knowledge.analogs import AnalogLibrary

    empty_events = trained_orchestrator.ge.iloc[0:0]  # no history at all
    lib = AnalogLibrary(trained_orchestrator.pt, empty_events)
    values, analogs = lib.find_analogs("GradeA", "GradeD", t_sec=300)
    assert values == {}
    assert analogs.transition_ids == []
