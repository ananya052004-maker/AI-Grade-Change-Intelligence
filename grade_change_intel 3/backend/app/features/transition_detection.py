"""
transition_detection.py
FR-02: detect the start of a grade transition within 10s, using GC_START when
available, else change-point detection on BW_SP (A-3's own stated fallback).
FR-03: assign a stable transition_id and bind everything to it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def detect_changepoint_on_bw_sp(bw_sp: np.ndarray, dt_s: float, rate_threshold: float = 0.03,
                                 sustain_scans: int = 3) -> int | None:
    """A-3 fallback: no GC_START event available. Flags the first index where
    |d(BW_SP)/dt| exceeds `rate_threshold` (gsm/s) and stays elevated for
    `sustain_scans` consecutive samples -- i.e. the setpoint trajectory has
    genuinely started ramping, not just scanner/setpoint noise.
    """
    roc = np.diff(bw_sp, prepend=bw_sp[0]) / dt_s
    elevated = np.abs(roc) > rate_threshold
    run = 0
    for i, e in enumerate(elevated):
        run = run + 1 if e else 0
        if run >= sustain_scans:
            return i - sustain_scans + 1
    return None


def detect_transition_start(bw_sp: np.ndarray, dt_s: float, gc_start_idx: int | None = None) -> tuple[int | None, str]:
    """Returns (start_idx, method). Prefers the explicit GC_START event; falls
    back to change-point detection, matching A-3 exactly."""
    if gc_start_idx is not None:
        return gc_start_idx, "GC_START_EVENT"
    idx = detect_changepoint_on_bw_sp(bw_sp, dt_s)
    return idx, "CHANGE_POINT_ON_BW_SP" if idx is not None else "NOT_DETECTED"


def assign_transition_id(event_id: str) -> str:
    """FR-03: stable id every prediction/suggestion/feedback binds to. In this
    MVP the upstream grade_events feed already carries a stable transition_id
    (our `event_id`); this function is the single place that name is minted
    from, so nothing downstream hard-codes the source field."""
    return event_id
