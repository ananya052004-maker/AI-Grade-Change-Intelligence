"""
optimizer.py
M6: "Bounded grid/CMA-ES over <=3 handles on the forward model -- small
action space; deterministic; explainable; no solver dependency risk" (Sec
7.3). Implemented as a bounded coordinate-wise grid search that moves each
candidate handle toward the value historical fast-stabilizing analogs used
at this stage of the ramp (app.knowledge.analogs), discretized into steps
rather than jumping straight to the target -- this is what keeps a
recommendation "bounded" (FR-12) instead of proposing an arbitrary leap.

FR-15: if the top-ranked handle is already saturated (constraint proximity
> 0.95 or < 0.05, meaning the MPC has it pinned near a limit), this module
does not recommend on it -- it redirects to the next-ranked handle and says
so, which is exactly E-11's required behaviour.
"""

from __future__ import annotations

import numpy as np

from app.config import get_actuator_limits


def rank_handles_by_impact(impact_ranking: "pd.DataFrame", handles: list[str], max_handles: int = 3) -> list[str]:
    """Sec 6.3 FR-12 caps the action space at <=3 handles; use the
    stabilization-impact ranking (FR-29) to decide which ones matter most."""
    ranked = impact_ranking[impact_ranking["variable"].isin(handles)].copy()
    ranked["abs_impact"] = ranked["impact_on_stabilization_time"].abs()
    ranked = ranked.sort_values("abs_impact", ascending=False)
    ordered = ranked["variable"].tolist()
    for h in handles:  # keep any handle impact ranking didn't cover, at the end
        if h not in ordered:
            ordered.append(h)
    return ordered[:max_handles]


def redirect_saturated_handles(candidate_handles: list[str], saturation: dict[str, bool]) -> tuple[list[str], list[str]]:
    """FR-15 / E-11: separate handles that are already at/near a physical
    limit from those that aren't; callers recommend on the latter and name
    the former explicitly rather than silently dropping them."""
    usable = [h for h in candidate_handles if not saturation.get(h, False)]
    saturated = [h for h in candidate_handles if saturation.get(h, False)]
    return usable, saturated


def bounded_grid_search(current_values: dict[str, float], target_values: dict[str, float],
                         handles: list[str], n_steps: int = 4) -> dict[str, float]:
    """For each handle, search a bounded grid of step sizes toward the
    analog target and return the closest reachable grid point -- never the
    raw target itself, so a single suggestion never proposes an
    arbitrarily large jump."""
    limits = get_actuator_limits()
    result = {}
    for h in handles:
        cur = current_values.get(h)
        tgt = target_values.get(h)
        if cur is None or tgt is None:
            continue
        max_rate = limits[h]["ramp_rate_max_per_s"]
        cycle_s = 5  # one prediction cycle (Appendix B predict.cycle_s)
        step = max_rate * cycle_s * 0.5  # half the max allowed ramp per cycle, per grid step
        direction = np.sign(tgt - cur)
        best_val, best_dist = cur, abs(tgt - cur)
        for k in range(1, n_steps + 1):
            candidate = cur + direction * step * k
            dist = abs(tgt - candidate)
            if dist <= best_dist:
                best_val, best_dist = candidate, dist
            if abs(candidate - tgt) < step:
                break
        result[h] = float(best_val)
    return result
