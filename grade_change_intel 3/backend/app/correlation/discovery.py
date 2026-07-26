"""
discovery.py
M4: FR-23..29 correlation discovery. This evolves the per-event correlation
fix already applied to the Streamlit prototype's intelligence_engine.py
earlier in this session (the bug where correlating context variables at the
timestep level against instantaneous deviation washed out their real signal)
into the PRD's stricter requirements: lagged cross-correlation over 0-300s,
a Benjamini-Hochberg FDR gate, a minimum-support count, and a known/novel
split against config/known_relationships.yaml.

Anti-requirement (Sec 6.5): "the System MUST NOT present an unqualified
correlation as an action driver." FR-25's gate exists specifically because
naive scanning of many tags produces spurious correlations by construction.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.stats import pearsonr

from app.config import get_known_relationships, get_settings
from app.contracts import CorrelationItem, CorrelationLabel, CorrelationSet
from app.features.feature_engine import ALL_NUMERIC, MANIPULATED

CANDIDATE_VARS = [v for v in ALL_NUMERIC if v not in ("BW_MEAS", "BW_SP")]


def benjamini_hochberg(p_values: list[float], q: float) -> list[bool]:
    """FR-25: FDR-corrected significance. Standard BH step-up procedure,
    implemented directly (no statsmodels dependency) since it's ~10 lines."""
    m = len(p_values)
    if m == 0:
        return []
    order = np.argsort(p_values)
    sorted_p = np.array(p_values)[order]
    thresholds = (np.arange(1, m + 1) / m) * q
    passed = sorted_p <= thresholds
    if not passed.any():
        cutoff_rank = -1
    else:
        cutoff_rank = np.max(np.where(passed))
    result = np.zeros(m, dtype=bool)
    if cutoff_rank >= 0:
        result[order[: cutoff_rank + 1]] = True
    return result.tolist()


def lagged_cross_correlation(series_a: np.ndarray, series_b: np.ndarray, dt_s: int,
                              max_lag_s: int) -> tuple[int, float]:
    """FR-23: scan lags 0..max_lag_s, return (best_lag_s, correlation) of the
    strongest |r| between series_a (leading) and series_b."""
    max_lag = int(max_lag_s / dt_s)
    best_lag, best_r = 0, 0.0
    for lag in range(0, max_lag + 1):
        if lag == 0:
            a, b = series_a, series_b
        else:
            a, b = series_a[:-lag], series_b[lag:]
        if len(a) < 10 or np.std(a) == 0 or np.std(b) == 0:
            continue
        r = np.corrcoef(a, b)[0, 1]
        if not np.isnan(r) and abs(r) > abs(best_r):
            best_lag, best_r = lag, r
    return best_lag * dt_s, float(best_r)


def _known_pairs() -> set[tuple[str, str]]:
    return {(kr["variable"], "BW_MEAS") for kr in get_known_relationships()}


def _tag_to_grade_variable(tag: str) -> str | None:
    mapping = {"STOCK_FLOW": "STOCK_FLOW", "FILLER_FLOW": "FILLER_FLOW",
               "STEAM_PRESS_G1": "STEAM_PRESS_G1", "MACHINE_SPEED": "MACHINE_SPEED"}
    return mapping.get(tag)


def discover_correlations(wide_by_event: dict[str, pd.DataFrame], target: str = "bw_deviation_pct",
                           impact_target_2: str = "t_stab_s") -> CorrelationSet:
    """Per PRD Sec 6.5. Correlates PER-EVENT aggregates (not per-timestep --
    that was this session's earlier bug fix in the Streamlit prototype),
    now with proper lagged cross-correlation, FDR gating, and known/novel
    labelling against config/known_relationships.yaml.

    wide_by_event: {event_id: wide feature dataframe (from feature_engine)},
                    time-ordered by insertion (caller sorts by ts_start), each
                    carrying a scalar `t_stab_s` column (broadcast across the
                    event's rows) for impact quantification.

    Two distinct questions get asked, deliberately not conflated (an earlier
    version of this function collapsed them into one nonsensical comparison):
      1. STRENGTH -- across the population of events, does this variable's
         own per-event behaviour (ramp-window aggressiveness) associate with
         worse outcomes (worse |deviation| / longer t_stab)? This is what
         gates novelty (FR-25) and drives impact quantification (FR-26).
      2. LAG -- within a single event's own timecourse, at what delay does
         this variable's level best track |deviation|? (FR-23). Reported as
         a median across events, purely informational/diagnostic.
    """
    settings = get_settings()
    dt_s = settings.data.resample_s
    known_pairs = _known_pairs()

    per_event_rows = []
    for event_id, wide in wide_by_event.items():
        max_abs_dev = wide[target].abs().max()
        t_stab = wide[impact_target_2].iloc[0] if impact_target_2 in wide.columns else np.nan
        row = {"event_id": event_id, "max_abs_dev": max_abs_dev, "t_stab_s": t_stab}

        ramp_mask = wide["phase"].astype(str).str.contains("RAMP") if "phase" in wide.columns else None
        for var in CANDIDATE_VARS:
            roc_col = f"{var}_roc"
            if roc_col not in wide.columns:
                continue
            window = wide.loc[ramp_mask, roc_col] if ramp_mask is not None and ramp_mask.any() else wide[roc_col]
            aggressiveness = float(window.std())
            row[f"{var}__agg"] = aggressiveness

            if var in wide.columns and np.std(wide[var].values) > 0:
                lag_s, _ = lagged_cross_correlation(wide[var].values, wide[target].abs().values, dt_s,
                                                     settings.correlation.max_lag_s)
                row[f"{var}__lag"] = lag_s
        per_event_rows.append(row)

    per_event = pd.DataFrame(per_event_rows)
    n_support = len(per_event)
    half = max(n_support // 2, 1)
    first_half, second_half = per_event.iloc[:half], per_event.iloc[half:]

    p_values, var_names, r_values = [], [], []
    for var in CANDIDATE_VARS:
        col = f"{var}__agg"
        if col not in per_event.columns:
            continue
        valid = per_event.dropna(subset=[col, "max_abs_dev"])
        valid = valid[valid[col].notna() & (valid[col] != 0)]
        if len(valid) < 3 or valid[col].std() == 0:
            continue
        r, p = pearsonr(valid[col], valid["max_abs_dev"])
        p_values.append(p)
        var_names.append(var)
        r_values.append(r)

    passed = dict(zip(var_names, benjamini_hochberg(p_values, settings.correlation.fdr_q)))
    q_by_var = dict(zip(var_names, p_values))
    strength_by_var = dict(zip(var_names, r_values))

    items = []
    for var in var_names:
        col = f"{var}__agg"
        valid = per_event.dropna(subset=[col])
        strength = strength_by_var[var]
        support_n = int(len(valid))
        median_lag = int(np.median(valid[f"{var}__lag"].dropna())) if f"{var}__lag" in valid.columns and valid[f"{var}__lag"].notna().any() else 0

        fh = first_half[col].dropna()
        sh = second_half[col].dropna()
        stable = (len(fh) >= 3 and len(sh) >= 3 and
                  np.sign(fh.corr(first_half.loc[fh.index, "max_abs_dev"]) or 0) ==
                  np.sign(sh.corr(second_half.loc[sh.index, "max_abs_dev"]) or 0))

        gate_passed = passed.get(var, False) and support_n >= settings.correlation.min_support_transitions and stable

        variable_key = _tag_to_grade_variable(var)
        is_known = (variable_key, "BW_MEAS") in known_pairs if variable_key else False
        novel = gate_passed and not is_known

        # FR-26: impact in engineering units.
        impact_gsm = float(valid["max_abs_dev"].mean()) if (novel or is_known) else None
        t_stab_corr = None
        tvalid = per_event.dropna(subset=[col, "t_stab_s"])
        if len(tvalid) >= 3 and tvalid[col].std() > 0:
            t_stab_corr, _ = pearsonr(tvalid[col], tvalid["t_stab_s"])

        # FR-27: future-state projection.
        projection = None
        if gate_passed:
            projection = {
                "assumption": "variable continues its currently-observed ramp-window aggressiveness",
                "projected_relationship": f"a +1 std-dev increase in {var}'s ramp aggressiveness historically "
                                           f"associates with r={strength:+.2f} shift in max |BW deviation|",
            }

        items.append(CorrelationItem(
            tag=var, lag_s=median_lag, strength=round(strength, 3), effect_size=round(abs(strength), 3),
            novel=novel, known_relationship_ref=(f"{variable_key}->BW_MEAS" if is_known else None),
            support_n=support_n, q_value=round(float(q_by_var[var]), 5),
            impact_gsm=round(impact_gsm, 3) if impact_gsm is not None else None,
            impact_t_stab_s=round(float(t_stab_corr), 3) if t_stab_corr is not None else None,
            projection=projection,
            label=CorrelationLabel.CORRELATION,
            passed_fdr_gate=gate_passed,
        ))

    items.sort(key=lambda it: abs(it.strength), reverse=True)
    return CorrelationSet(computed_at=datetime.now(timezone.utc), items=items)


def stabilization_impact_ranking(wide_by_event: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """FR-29: rank loops/parameters by impact on stabilization time, so the
    dashboard can suggest which handle to prioritise for faster stabilization."""
    rows = []
    for event_id, wide in wide_by_event.items():
        if "t_stab_s" not in wide.columns:
            continue
        t_stab = wide["t_stab_s"].iloc[0]
        row = {"event_id": event_id, "t_stab_s": t_stab}
        for var in MANIPULATED + ["MOIST_MEAS", "ASH_MEAS", "CALIPER_MEAS"]:
            roc_col = f"{var}_roc"
            if roc_col in wide.columns:
                row[var] = wide[roc_col].std()
        rows.append(row)
    df = pd.DataFrame(rows).dropna(subset=["t_stab_s"])
    results = []
    for var in MANIPULATED + ["MOIST_MEAS", "ASH_MEAS", "CALIPER_MEAS"]:
        if var not in df.columns or df[var].std() == 0:
            continue
        valid = df.dropna(subset=[var])
        if len(valid) < 3:
            continue
        r, p = pearsonr(valid[var], valid["t_stab_s"])
        results.append({"variable": var, "impact_on_stabilization_time": round(r, 3), "p_value": round(p, 5)})
    return pd.DataFrame(results).sort_values("impact_on_stabilization_time", key=abs, ascending=False)
