"""
contracts.py
Pydantic models for the canonical data contract (PRD §5.1) and every inter-module
edge in the architecture (PRD §7.2). This file is the integration boundary: every
module talks to every other module only through these types, never through ad hoc
dicts. Unknown fields are rejected, not ignored (extra="forbid") -- per §7.2's note
that "unknown feature => reject, not ignore" for FeatureVector, generalised here to
all edges, since a silently-ignored field is exactly the kind of unattributed
behaviour §4.2 C-5 prohibits.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# §5.1 canonical data contract
# ---------------------------------------------------------------------------

class Quality(str, Enum):
    GOOD = "GOOD"
    UNCERTAIN = "UNCERTAIN"
    BAD = "BAD"
    STALE = "STALE"


class ProcessTimeseriesRow(StrictModel):
    """§5.1.1 process_timeseries -- one (ts, machine_id, tag) observation."""
    ts: datetime
    machine_id: str
    tag: str
    value: float
    unit: str
    quality: Quality = Quality.GOOD


class Trigger(str, Enum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class EventOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"
    FAILURE = "FAILURE"
    ABORTED = "ABORTED"      # E-08 sheet break mid-transition
    REVERSED = "REVERSED"    # E-09 operator reverses the grade change


class GradeEvent(StrictModel):
    """§5.1.2 grade_events"""
    ts_start: datetime
    ts_end: Optional[datetime] = None
    machine_id: str
    grade_from: str
    grade_to: str
    transition_id: str
    trigger: Trigger
    outcome: EventOutcome
    chained: bool = False          # E-10 two grade changes back-to-back
    confounded: bool = False       # E-15 concurrent trim/reel change


class RecipeLimit(StrictModel):
    """§5.1.3 recipe_limits"""
    grade_id: str
    variable: str
    setpoint: float
    lo_spec: float
    hi_spec: float
    lo_alarm: float
    hi_alarm: float
    ramp_rate_max: float
    source: str = "RECIPE"


class ActionType(str, Enum):
    SETPOINT_NUDGE = "SETPOINT_NUDGE"
    MODE_CHANGE = "MODE_CHANGE"
    OTHER = "OTHER"


class OperatorAction(StrictModel):
    """§5.1.4 operator_actions"""
    ts: datetime
    machine_id: str
    operator_id: str  # pseudonymised (SEC-02)
    tag: str
    old_value: float
    new_value: float
    action_type: ActionType
    free_text: str = ""


class FeedbackResponse(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"
    ACCEPTED_NOT_EXECUTED = "ACCEPTED_NOT_EXECUTED"  # E-18


class RejectReason(str, Enum):
    UNSAFE = "UNSAFE"
    WRONG_HANDLE = "WRONG_HANDLE"
    TOO_LATE = "TOO_LATE"
    ALREADY_DOING_IT = "ALREADY_DOING_IT"
    DISAGREE_WITH_DIAGNOSIS = "DISAGREE_WITH_DIAGNOSIS"
    NOT_APPLICABLE_TO_THIS_GRADE = "NOT_APPLICABLE_TO_THIS_GRADE"
    OTHER = "OTHER"


class SuggestionFeedback(StrictModel):
    """§5.1.5 suggestion_feedback -- written by the System, append-only (FR-33)."""
    suggestion_id: str
    ts_issued: datetime
    ts_responded: Optional[datetime] = None
    transition_id: str
    type: str
    payload_json: str
    sources_json: str
    predicted_effect_json: str
    response: Optional[FeedbackResponse] = None
    reject_reason: Optional[RejectReason] = None
    operator_id: Optional[str] = None
    realised_effect_json: Optional[str] = None
    model_version: str


# ---------------------------------------------------------------------------
# §7.2 inter-module contracts
# ---------------------------------------------------------------------------

class Frame(StrictModel):
    """M1->M2. Fixed 5s cadence; gaps are explicit (missing tag keys), never
    silently interpolated as if continuous (DR-06)."""
    ts: datetime
    machine_id: str
    tags: dict[str, "TagSample"]


class TagSample(StrictModel):
    value: float
    quality: Quality
    age_since_scan_s: Optional[float] = None  # scanner variables (DR-06)


Frame.model_rebuild()


class Phase(str, Enum):
    PRE_CHECK = "PRE_CHECK"
    RAMP = "RAMP"
    SETTLE = "SETTLE"
    STEADY = "STEADY"


class FeatureVector(StrictModel):
    """M2->M3/M4. Feature names are a versioned schema; an unknown feature key
    must be rejected upstream, not silently ignored (§7.2)."""
    ts: datetime
    transition_id: str
    phase: Phase
    schema_version: str
    features: dict[str, float]
    staleness: dict[str, bool] = Field(default_factory=dict)


class RiskState(str, Enum):
    OK = "OK"
    WATCH = "WATCH"
    AT_RISK = "AT_RISK"
    CRITICAL = "CRITICAL"
    NO_PREDICTION = "NO_PREDICTION"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"  # NFR-M7 unseen grade pair


class Attribution(StrictModel):
    feature: str
    shap_value: float
    direction: str  # "increases risk" | "decreases risk"


class Trajectory(StrictModel):
    t_s: list[float]
    p10: list[float]
    p50: list[float]
    p90: list[float]


class RiskAssessment(StrictModel):
    """M3->M6."""
    transition_id: str
    ts: datetime
    p_offspec: dict[str, float]  # horizon_s (as str key) -> probability, e.g. {"60":.., "180":.., "300":..}
    trajectory: Optional[Trajectory] = None
    state: RiskState
    reason: Optional[str] = None  # populated when state == NO_PREDICTION (FR-10)
    attribution: list[Attribution] = Field(default_factory=list)
    model_version: str
    calibrated: bool = True
    staleness_penalised: bool = False  # E-21


class SourceType(str, Enum):
    RECIPE = "RECIPE"
    HISTORICAL_ANALOG = "HISTORICAL_ANALOG"
    CORRELATION_MODEL = "CORRELATION_MODEL"
    PHYSICS_MODEL = "PHYSICS_MODEL"
    OPERATOR_PRECEDENT = "OPERATOR_PRECEDENT"
    ALARM_CONTEXT = "ALARM_CONTEXT"
    SIMULATION = "SIMULATION"
    INFERRED_FROM_HISTORY = "INFERRED_FROM_HISTORY"


class Source(StrictModel):
    """FR-18. Every prediction/recommendation carries sources[]; non-empty is a
    hard invariant (M-6, AC-4)."""
    type: SourceType
    reference: str
    weight: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


class CorrelationLabel(str, Enum):
    CORRELATION = "CORRELATION"
    LIKELY_CAUSAL = "LIKELY_CAUSAL"


class CorrelationItem(StrictModel):
    tag: str
    lag_s: int
    strength: float
    effect_size: float
    novel: bool
    known_relationship_ref: Optional[str] = None
    support_n: int
    q_value: float
    impact_gsm: Optional[float] = None
    impact_t_stab_s: Optional[float] = None
    projection: Optional[dict] = None  # FR-27: future-state trend projection
    label: CorrelationLabel = CorrelationLabel.CORRELATION
    passed_fdr_gate: bool = False


class CorrelationSet(StrictModel):
    """M4->M6/M9."""
    transition_id: Optional[str] = None
    computed_at: datetime
    items: list[CorrelationItem]


class Constraints(StrictModel):
    """M5->M6."""
    recipe_limits: list[RecipeLimit]
    actuator_ranges: dict[str, list[float]]
    ramp_limits: dict[str, float]


class Analogs(StrictModel):
    transition_ids: list[str]
    outcomes: list[str]


class CandidateSuggestion(StrictModel):
    """M6->M7. Infeasible candidates pass through labelled (feasible=False), so
    the UI can explain suppression rather than silently dropping them (FR-14)."""
    tag: str
    from_value: float
    to_value: float
    ramp_rate: float
    predicted_effect: dict
    feasible: bool
    binding_constraint: Optional[str] = None


class Suggestion(StrictModel):
    """M7->M8. sources[] non-empty is a hard invariant (M-6)."""
    id: str
    transition_id: str
    ts_issued: datetime
    type: str
    candidates: list[CandidateSuggestion]
    sources: list[Source]
    rationale_text: str = Field(max_length=400)  # ~40 words (FR-19)
    confidence: float = Field(ge=0.0, le=1.0)
    model_version: str
    ttl_s: int
    expires_at: datetime


class Feedback(StrictModel):
    """M9->M10."""
    suggestion_id: str
    response: FeedbackResponse
    reason: Optional[RejectReason] = None
    operator_id: str
    ts: datetime


class EvaluationRecord(StrictModel):
    """M10->M11."""
    suggestion_id: str
    transition_id: str
    went_offspec: bool
    t_stab_s: Optional[float]
    classification: str  # "TRUE_POSITIVE_PREVENTED" | "FALSE_ALARM" | "MISS" | "ACCEPTED_NOT_EXECUTED" | ...
    model_version: str
