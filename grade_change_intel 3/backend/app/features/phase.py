"""
phase.py
FR-04: classify transition phase PRE_CHECK -> RAMP -> SETTLE -> STEADY from
signal alone (BW_SP rate of change + BW_MEAS proximity to final target),
deliberately not from any out-of-band "we already know how this event ends"
information, so the same function works identically online and offline.
"""

from __future__ import annotations

import numpy as np

from app.contracts import Phase


def classify_phase_series(bw_sp: np.ndarray, bw_meas: np.ndarray, dt_s: float,
                           final_target: float, band_pct: float = 1.0,
                           rate_threshold: float = 0.03) -> np.ndarray:
    """Vectorized phase classification over a whole transition window.
    PRE_CHECK: BW_SP not yet moving.
    RAMP:      |d(BW_SP)/dt| above threshold.
    SETTLE:    BW_SP has reached final value but BW_MEAS not yet within band.
    STEADY:    BW_MEAS within +-band_pct of the final target.
    """
    n = len(bw_sp)
    roc = np.diff(bw_sp, prepend=bw_sp[0]) / dt_s
    ramping = np.abs(roc) > rate_threshold
    sp_at_final = np.abs(bw_sp - final_target) < 1e-6
    within_band = np.abs(100 * (bw_meas - final_target) / final_target) < band_pct

    phases = np.empty(n, dtype=object)
    started = False
    for i in range(n):
        if ramping[i]:
            started = True
        if not started:
            phases[i] = Phase.PRE_CHECK
        elif not sp_at_final[i]:
            phases[i] = Phase.RAMP
        elif within_band[i]:
            phases[i] = Phase.STEADY
        else:
            phases[i] = Phase.SETTLE
    return phases


def classify_phase_at(bw_sp_history: np.ndarray, bw_meas_history: np.ndarray, dt_s: float,
                       final_target: float, band_pct: float = 1.0) -> Phase:
    """Online variant: given the history up to and including now, return the
    current phase only (last element of the vectorized classification)."""
    return classify_phase_series(bw_sp_history, bw_meas_history, dt_s, final_target, band_pct)[-1]
