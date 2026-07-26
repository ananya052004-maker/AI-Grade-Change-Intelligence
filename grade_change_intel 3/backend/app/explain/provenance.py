"""
provenance.py
M7: assembles the structured sources[] array (FR-18) and generates the
<=40-word operator-facing rationale FR-19 requires -- FR-22 is the
constraint that makes this module's shape non-negotiable: "Rationale text
MUST be generated from the structured sources[] object. Free-text
generation not grounded in that object is prohibited." So build_rationale()
below only ever reads fields off the Source/Attribution objects it's given;
it never has an LLM or template with room to invent a fact that isn't in
sources[].
"""

from __future__ import annotations

from app.contracts import Attribution, CorrelationItem, Source, SourceType


def source_from_shap(attribution: list[Attribution], model_version: str) -> Source:
    top = attribution[0] if attribution else None
    confidence = min(1.0, abs(top.shap_value) * 4) if top else 0.3
    return Source(type=SourceType.CORRELATION_MODEL, reference=f"risk_model:{model_version}",
                  weight=0.6, confidence=round(confidence, 2))


def source_from_analog(n_events: int, analog_source_tag: str) -> Source:
    confidence = min(1.0, 0.3 + 0.07 * n_events)
    return Source(type=SourceType.HISTORICAL_ANALOG, reference=analog_source_tag,
                  weight=0.7, confidence=round(confidence, 2))


def source_from_recipe(grade_id: str, variable: str) -> Source:
    return Source(type=SourceType.RECIPE, reference=f"recipe:{grade_id}:{variable}",
                  weight=1.0, confidence=1.0)


def source_from_correlation(item: CorrelationItem) -> Source:
    return Source(type=SourceType.CORRELATION_MODEL,
                  reference=f"correlation:{item.tag}:lag{item.lag_s}s:n{item.support_n}",
                  weight=min(1.0, item.effect_size), confidence=round(1 - item.q_value, 2) if item.q_value <= 1 else 0.5)


def source_from_physics(model_version: str) -> Source:
    return Source(type=SourceType.PHYSICS_MODEL, reference=f"trajectory_model:{model_version}",
                  weight=0.5, confidence=0.6)


def build_rationale(attribution: list[Attribution], risk_pct: float, n_analogs: int,
                     analog_outcome_rate: float | None, binding_constraint: str | None = None) -> str:
    """FR-19: <=40 words, grounded only in the fields passed in (which
    themselves came from sources[] upstream) -- e.g.:
    'Steam group 3 is within 4% of its high limit while speed is still
    ramping; in 12 of 14 similar transitions this produced an excursion.'
    """
    parts = []
    if attribution:
        top = attribution[0]
        parts.append(f"{top.feature} is the top driver, {top.direction} ({top.shap_value:+.3f})")
    if len(attribution) > 1:
        parts.append(f"with {attribution[1].feature} also contributing")
    parts.append(f"risk of sustained off-spec is {risk_pct:.0f}%")
    if n_analogs:
        rate_txt = f", {analog_outcome_rate:.0%} of {n_analogs} similar transitions stabilized" if analog_outcome_rate is not None else f", based on {n_analogs} similar historical transitions"
        parts.append(rate_txt.strip(", "))
    if binding_constraint:
        parts.append(f"note: {binding_constraint} is binding on the top-ranked handle")
    text = "; ".join(parts) + "."
    words = text.split()
    if len(words) > 40:
        text = " ".join(words[:40]) + "."
    return text


def assemble_sources(attribution: list[Attribution], model_version: str,
                      n_analog_events: int | None, analog_source_tag: str | None,
                      recipe_grade_id: str | None = None, recipe_variable: str | None = None,
                      novel_correlations: list[CorrelationItem] | None = None) -> list[Source]:
    """M-6 / AC-4: sources[] non-empty is a hard invariant -- this function
    always returns at least one Source, falling back to the model itself if
    nothing else is available."""
    sources = [source_from_shap(attribution, model_version)]
    if n_analog_events and analog_source_tag:
        sources.append(source_from_analog(n_analog_events, analog_source_tag))
    if recipe_grade_id and recipe_variable:
        sources.append(source_from_recipe(recipe_grade_id, recipe_variable))
    for item in (novel_correlations or []):
        sources.append(source_from_correlation(item))
    return sources
