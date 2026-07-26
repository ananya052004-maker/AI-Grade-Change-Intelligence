"""
safety_gate.py
SAF-01: "The safety gate MUST be a separate module with no ML dependency, so
limit enforcement cannot be degraded by a model change." Check the imports
below -- there are none from app.models or any ML library, by design, and
that constraint is exactly what makes this file trustworthy to review in
isolation.

FR-14: any recommendation whose value or ramp would violate a hard limit
MUST be suppressed and replaced with an explicit message naming the binding
constraint. Silent clipping is prohibited -- this module never clips a
value, it only ever accepts or rejects one, with a reason.
"""

from __future__ import annotations

from app.contracts import CandidateSuggestion, Constraints


def check_candidate(tag: str, current_value: float, proposed_value: float, dt_s: float,
                     constraints: Constraints, recipe_grade_id: str | None = None) -> CandidateSuggestion:
    ramp_rate = abs(proposed_value - current_value) / dt_s

    # 1. Actuator physical range (C-1: actuator ranges).
    if tag in constraints.actuator_ranges:
        lo, hi = constraints.actuator_ranges[tag]
        if proposed_value < lo or proposed_value > hi:
            return CandidateSuggestion(tag=tag, from_value=current_value, to_value=proposed_value,
                                        ramp_rate=ramp_rate, predicted_effect={}, feasible=False,
                                        binding_constraint=f"actuator_range[{lo},{hi}]")

    # 2. Ramp-rate limit (C-1: ramp-rate limits).
    if tag in constraints.ramp_limits:
        max_rate = constraints.ramp_limits[tag]
        if ramp_rate > max_rate:
            return CandidateSuggestion(tag=tag, from_value=current_value, to_value=proposed_value,
                                        ramp_rate=ramp_rate, predicted_effect={}, feasible=False,
                                        binding_constraint=f"ramp_rate_max[{max_rate}/s]")

    # 3. Recipe spec/alarm bounds, if this tag has a recipe entry (C-1: recipe limits).
    recipe_entry = next((r for r in constraints.recipe_limits if r.variable == tag), None)
    if recipe_entry is not None:
        if proposed_value < recipe_entry.lo_alarm or proposed_value > recipe_entry.hi_alarm:
            return CandidateSuggestion(tag=tag, from_value=current_value, to_value=proposed_value,
                                        ramp_rate=ramp_rate, predicted_effect={}, feasible=False,
                                        binding_constraint=f"recipe_alarm_band[{recipe_entry.lo_alarm},{recipe_entry.hi_alarm}]")

    return CandidateSuggestion(tag=tag, from_value=current_value, to_value=proposed_value,
                                ramp_rate=ramp_rate, predicted_effect={}, feasible=True, binding_constraint=None)


def filter_feasible(candidates: list[CandidateSuggestion]) -> tuple[list[CandidateSuggestion], list[CandidateSuggestion]]:
    """Returns (feasible, suppressed). Suppressed candidates are NOT dropped
    silently -- callers must surface them with their binding_constraint
    (FR-14), which is why this returns both lists rather than filtering."""
    feasible = [c for c in candidates if c.feasible]
    suppressed = [c for c in candidates if not c.feasible]
    return feasible, suppressed
