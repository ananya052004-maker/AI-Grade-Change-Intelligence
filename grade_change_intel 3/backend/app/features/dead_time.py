"""
dead_time.py
FR-07 / A-4: estimate sheet transport dead time theta by cross-correlating a
manipulated-variable's rate of change against the BW response, per grade
pair, so the risk model can be trained on dead-time-aligned features -- i.e.
so it predicts what will arrive at the scanner rather than reacting to what
the scanner already saw.
"""

from __future__ import annotations

import numpy as np


def estimate_dead_time_s(stock_flow: np.ndarray, bw_meas: np.ndarray, dt_s: float,
                          max_lag_s: float = 90) -> float:
    """Cross-correlate d(stock_flow)/dt against d(bw_meas)/dt over lags
    [0, max_lag_s] and return the lag (seconds) of maximum correlation --
    the empirical transport delay for this transition.
    """
    max_lag = int(max_lag_s / dt_s)
    x = np.diff(stock_flow, prepend=stock_flow[0])
    y = np.diff(bw_meas, prepend=bw_meas[0])
    x = (x - x.mean()) / (x.std() + 1e-9)
    y = (y - y.mean()) / (y.std() + 1e-9)

    best_lag, best_corr = 0, -np.inf
    for lag in range(0, max_lag + 1):
        if lag == 0:
            xs, ys = x, y
        else:
            xs, ys = x[:-lag], y[lag:]
        if len(xs) < 10:
            break
        corr = float(np.corrcoef(xs, ys)[0, 1])
        if not np.isnan(corr) and corr > best_corr:
            best_corr, best_lag = corr, lag
    return best_lag * dt_s


def estimate_dead_time_per_grade_pair(events_df, ts_pivot_fn, dt_s: float) -> dict:
    """events_df: grade_events DataFrame. ts_pivot_fn(event_id) -> wide DataFrame
    with STOCK_FLOW/BW_MEAS columns. Returns {(from_grade,to_grade): median_theta_s}."""
    from collections import defaultdict
    samples = defaultdict(list)
    for _, ev in events_df.iterrows():
        wide = ts_pivot_fn(ev["transition_id"])
        if wide is None or "STOCK_FLOW" not in wide or "BW_MEAS" not in wide:
            continue
        theta = estimate_dead_time_s(wide["STOCK_FLOW"].values, wide["BW_MEAS"].values, dt_s)
        samples[(ev["grade_from"], ev["grade_to"])].append(theta)
    return {pair: float(np.median(v)) for pair, v in samples.items() if v}
