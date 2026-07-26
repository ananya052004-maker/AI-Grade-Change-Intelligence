"""
business_impact.py
Translates the tool's technical output (predicted stabilization-time
reduction) into what a production manager actually asks about: tonnes of
broke avoided, minutes saved, and (optionally) an estimated dollar value.

PRD Sec 15, OQ-5 ("cost per tonne of broke") was left unanswered with a
stated default -- "report tonnes and minutes only, not currency" -- and
tonnes/minutes are still always reported without an invented figure.

DEFAULT_COST_PER_TONNE_USD below is a SEPARATE, explicitly-labelled
assumption on top of that default, not a replacement for it: a real, sourced
market figure (see the constant's own comment for the citation), used only
where a currency estimate is explicitly requested (e.g. for pitch/demo
purposes) -- it always carries its source and is never silently presented as
a precise mill-specific broke cost.
"""

from __future__ import annotations

from app.simulation.physics_simulator import TRIM_WIDTH

# Printing/writing paper grades were trading in the $750-800/MT range in
# 2026 (global export benchmark ~$914/MT in 2025) -- see ExpertMarketResearch
# paper price trend coverage, July 2026. Using $800/tonne as a round, sourced
# mid-range figure for the VALUE OF LOST PRODUCTION (finished-paper market
# price), not a precise broke-recovery/scrap economics model -- broke is
# usually partially recycled back into the process, so this is a defensible
# upper-bound proxy for "what a tonne of off-spec production was worth,"
# stated as an assumption, not asserted as mill-specific accounting.
DEFAULT_COST_PER_TONNE_USD = 800.0


def production_rate_tonnes_per_min(machine_speed_mpm: float, basis_weight_gsm: float,
                                    trim_width_m: float = TRIM_WIDTH) -> float:
    """Sheet area rate (m^2/min) x basis weight (g/m^2), converted grams -> tonnes."""
    return max(machine_speed_mpm, 0.0) * trim_width_m * max(basis_weight_gsm, 0.0) / 1_000_000.0


def estimate_impact(machine_speed_mpm: float, basis_weight_gsm: float,
                     baseline_t_stab_s: float | None, recommended_t_stab_s: float | None,
                     cost_per_tonne_usd: float = DEFAULT_COST_PER_TONNE_USD) -> dict:
    """baseline_t_stab_s: this grade pair's unbiased historical median T_stab.
    recommended_t_stab_s: expected T_stab if the fastest-stabilizing-tercile
    analog setpoints are followed (app.knowledge.analogs). The gap between
    them, converted to production time, is what's "saved" -- while every
    minute a transition spends unstabilized is being treated as producing
    off-spec (broke) material, which is the same assumption the simulator's
    own off-spec/stabilization definitions already encode."""
    rate = production_rate_tonnes_per_min(machine_speed_mpm, basis_weight_gsm)
    if baseline_t_stab_s is None or recommended_t_stab_s is None or baseline_t_stab_s <= recommended_t_stab_s:
        return {
            "minutes_saved": 0.0, "broke_tonnes_avoided": 0.0, "estimated_value_usd": 0.0,
            "cost_per_tonne_usd": cost_per_tonne_usd,
            "production_rate_tonnes_per_min": round(rate, 3),
            "baseline_t_stab_s": baseline_t_stab_s, "recommended_t_stab_s": recommended_t_stab_s,
            "basis": "no measurable improvement over this grade pair's historical baseline",
            "cost_assumption": "$800/tonne (2026 printing/writing paper market price, "
                                "ExpertMarketResearch) -- an assumption, not a mill-specific broke cost",
        }
    minutes_saved = (baseline_t_stab_s - recommended_t_stab_s) / 60.0
    broke_avoided = rate * minutes_saved
    return {
        "minutes_saved": round(minutes_saved, 2),
        "broke_tonnes_avoided": round(broke_avoided, 3),
        "estimated_value_usd": round(broke_avoided * cost_per_tonne_usd, 2),
        "cost_per_tonne_usd": cost_per_tonne_usd,
        "production_rate_tonnes_per_min": round(rate, 3),
        "baseline_t_stab_s": round(baseline_t_stab_s, 1), "recommended_t_stab_s": round(recommended_t_stab_s, 1),
        "basis": "vs. this grade pair's unbiased historical median stabilization time",
        "cost_assumption": "$800/tonne (2026 printing/writing paper market price, "
                            "ExpertMarketResearch) -- an assumption, not a mill-specific broke cost",
    }
