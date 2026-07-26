"""
engine.py
M6 orchestration: ties the analog library (M5), the bounded grid optimizer,
the safety gate (SAF-01), and the provenance/explanation module (M7) into a
single Suggestion. FR-16 rate limiting and FR-11's "only when risk >=
AT_RISK" gate both live here, since they're properties of *when* a
suggestion set is issued, not of any individual candidate.

E-19 (two suggestions with conflicting directions) is avoided by
construction rather than by a separate conflict detector: this engine issues
exactly one coherent suggestion set per rate-limit window from a single
bounded-grid-search result, so there is never a second, independently
generated candidate set to conflict with.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.config import get_settings
from app.contracts import RiskAssessment, RiskState, Suggestion
from app.explain.provenance import assemble_sources, build_rationale
from app.features.feature_engine import MANIPULATED
from app.knowledge.analogs import AnalogLibrary
from app.knowledge.recipe_limits import RecipeLimitsStore
from app.recommend.optimizer import bounded_grid_search, rank_handles_by_impact, redirect_saturated_handles
from app.recommend.safety_gate import check_candidate, filter_feasible


class RecommendationEngine:
    def __init__(self, analog_library: AnalogLibrary, recipe_store: RecipeLimitsStore):
        self.analog_library = analog_library
        self.recipe_store = recipe_store
        self.settings = get_settings()
        self._last_issued: dict[str, datetime] = {}
        self._active_suggestion_id: dict[str, str] = {}

    def maybe_generate(self, transition_id: str, from_grade: str, to_grade: str, t_sec: float,
                        current_values: dict[str, float], saturation: dict[str, bool],
                        risk_assessment: RiskAssessment, impact_ranking: pd.DataFrame,
                        model_version: str, now: datetime) -> tuple[Suggestion | None, str | None, str | None]:
        """Returns (suggestion_or_none, superseded_suggestion_id_or_none, no_suggestion_reason)."""
        last = self._last_issued.get(transition_id)
        if last and (now - last).total_seconds() < self.settings.suggest.min_interval_s:
            return None, None, "RATE_LIMITED"

        # FR-11: only when risk >= AT_RISK.
        if risk_assessment.state not in (RiskState.AT_RISK, RiskState.CRITICAL):
            return None, None, "RISK_BELOW_AT_RISK_THRESHOLD"

        analog_values, analogs = self.analog_library.find_analogs(from_grade, to_grade, t_sec)
        if not analog_values:
            return None, None, "INSUFFICIENT_HISTORICAL_MATCHES"

        source_tag = analog_values.pop("_source")
        n_events = analog_values.pop("_based_on_n_events")
        analog_values.pop("_expected_stabilization_time_sec", None)

        ranked = rank_handles_by_impact(impact_ranking, list(MANIPULATED), max_handles=self.settings.suggest.max_per_set)
        usable, saturated_handles = redirect_saturated_handles(ranked, saturation)
        if not usable:
            # FR-15: every top-ranked handle is saturated -- redirect to any handle
            # that isn't, rather than issuing nothing.
            fallback = [h for h in MANIPULATED if h not in ranked and not saturation.get(h, False)]
            usable = fallback[:1]
        if not usable:
            return None, None, "ALL_HANDLES_SATURATED"

        grid_result = bounded_grid_search(current_values, analog_values, usable)
        constraints = self.recipe_store.constraints_for(to_grade)

        candidates = [
            check_candidate(tag, current_values[tag], proposed, dt_s=self.settings.data.resample_s,
                             constraints=constraints, recipe_grade_id=to_grade)
            for tag, proposed in grid_result.items()
        ]
        feasible, suppressed = filter_feasible(candidates)
        if not feasible and not suppressed:
            return None, None, "NO_CANDIDATES_GENERATED"

        default_horizon = str(self.settings.predict.horizon_s)
        risk_pct = risk_assessment.p_offspec.get(default_horizon, 0.0) * 100
        analog_rate = (
            sum(1 for o in analogs.outcomes if o == "SUCCESS") / len(analogs.outcomes)
            if analogs.outcomes else None
        )
        binding = suppressed[0].binding_constraint if suppressed else None
        rationale = build_rationale(risk_assessment.attribution, risk_pct, n_events, analog_rate, binding)
        sources = assemble_sources(risk_assessment.attribution, model_version, n_events, source_tag,
                                    recipe_grade_id=to_grade)

        # E-15: if saturated handles were bypassed, note it as part of the redirect story.
        if saturated_handles:
            rationale = rationale.rstrip(".") + f"; {', '.join(saturated_handles)} already at limit, redirected."
            words = rationale.split()
            if len(words) > 40:
                rationale = " ".join(words[:40]) + "."

        # A plain second-resolution timestamp collides under concurrent requests
        # (two ticks landing in the same wall-clock second produce the same id
        # and the second INSERT fails suggestion_feedback's UNIQUE constraint) --
        # append a short random suffix so IDs stay unique under real concurrency.
        suggestion_id = f"SUG-{transition_id}-{int(now.timestamp())}-{uuid.uuid4().hex[:6]}"
        ttl_s = self.settings.suggest.ttl_s
        suggestion = Suggestion(
            id=suggestion_id, transition_id=transition_id, ts_issued=now, type="setpoint_recommendation",
            candidates=candidates, sources=sources, rationale_text=rationale,
            confidence=round(float(np.mean([s.confidence for s in sources])), 3),
            model_version=model_version, ttl_s=ttl_s, expires_at=now + timedelta(seconds=ttl_s),
        )
        superseded_id = self._active_suggestion_id.get(transition_id)
        self._last_issued[transition_id] = now
        self._active_suggestion_id[transition_id] = suggestion_id
        return suggestion, superseded_id, None
