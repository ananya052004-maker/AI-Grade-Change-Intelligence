"""
baselines.py
NFR-M3: "A naive baseline MUST be reported alongside every model result: (a)
always predict no event, (b) linear extrapolation of BW, (c) threshold-on-
current-deviation. A model that does not beat (c) is not shipped."
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def baseline_always_negative(n: int) -> np.ndarray:
    return np.zeros(n)


def baseline_linear_extrapolation(df: pd.DataFrame, horizon_scans: int, dt_s: int,
                                   spec_band_pct: float) -> np.ndarray:
    """Project BW forward at its current rate of change; predict positive if
    the projected deviation would exceed the spec band."""
    projected_bw = df["BW_MEAS"] + df["BW_MEAS_roc"] * horizon_scans * dt_s
    dev = 100 * (projected_bw - df["BW_SP"]) / df["BW_SP"]
    return (dev.abs() > spec_band_pct).astype(int).values


def baseline_threshold_on_current_deviation(df: pd.DataFrame, threshold_pct: float = 1.5) -> np.ndarray:
    """Predict positive if the transition is ALREADY drifting toward the
    band, using a tighter early-warning threshold than the 2.5% spec itself."""
    return (df["bw_deviation_pct"].abs() > threshold_pct).astype(int).values


def all_baselines(df: pd.DataFrame, horizon_scans: int, dt_s: int, spec_band_pct: float) -> dict:
    return {
        "always_negative": baseline_always_negative(len(df)),
        "linear_extrapolation": baseline_linear_extrapolation(df, horizon_scans, dt_s, spec_band_pct),
        "threshold_on_current_deviation": baseline_threshold_on_current_deviation(df),
    }
