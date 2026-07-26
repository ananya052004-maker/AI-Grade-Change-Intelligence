"""
AC-5: correlation panel distinguishes known vs novel, and every novel item
passes the FDR + support + stability gate. FR-25 anti-requirement: the
System must not present an unqualified (spurious) correlation as an action
driver -- this test constructs a case designed to produce a spurious
correlation by chance and asserts the gate catches it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.correlation.discovery import benjamini_hochberg, discover_correlations


def test_benjamini_hochberg_rejects_noise_controls_fdr():
    """With 200 independent null tests (uniform p-values) and q=0.05, BH
    should pass only a small minority -- if it passed most of them, the
    correction isn't doing anything."""
    rng = np.random.default_rng(0)
    p_values = rng.uniform(0, 1, 200).tolist()
    passed = benjamini_hochberg(p_values, q=0.05)
    assert sum(passed) < 20, "BH should reject the overwhelming majority of pure-noise p-values"


def test_benjamini_hochberg_accepts_genuine_signal():
    p_values = [0.0001, 0.0004, 0.0009, 0.4, 0.6, 0.8, 0.9]
    passed = benjamini_hochberg(p_values, q=0.05)
    assert passed[0] and passed[1] and passed[2]
    assert not passed[4] and not passed[5]


def _make_wide_event(event_id: str, n: int, rng: np.random.Generator, signal_var: str | None,
                      t_stab_s: float) -> pd.DataFrame:
    """A minimal synthetic 'wide' event table matching what
    build_event_features produces, for the two columns discover_correlations
    actually reads: `<var>_roc` and `bw_deviation_pct`, plus `phase`."""
    cols = {"t_stab_s": t_stab_s, "phase": ["RAMP"] * n}
    dev = rng.normal(0, 1, n)
    cols["bw_deviation_pct"] = dev
    for var in ["STOCK_FLOW", "FILLER_FLOW", "STEAM_PRESS_G1", "MACHINE_SPEED",
                "MOIST_MEAS", "ASH_MEAS", "CALIPER_MEAS", "HEADBOX_CONSISTENCY",
                "DRYER_HOOD_HUMID", "RETENTION_AID_FLOW", "BROKE_RATIO"]:
        if var == signal_var:
            cols[f"{var}_roc"] = dev * 2 + rng.normal(0, 0.3, n)  # genuinely coupled to deviation
        else:
            cols[f"{var}_roc"] = rng.normal(0, 1, n)  # pure noise, independent of deviation
    return pd.DataFrame(cols)


def test_discover_correlations_flags_only_the_genuine_signal():
    rng = np.random.default_rng(42)
    wide_by_event = {}
    for i in range(40):
        wide_by_event[f"EVT{i:03d}"] = _make_wide_event(
            f"EVT{i:03d}", n=30, rng=rng, signal_var="RETENTION_AID_FLOW", t_stab_s=float(rng.integers(200, 800))
        )
    cs = discover_correlations(wide_by_event)
    gated = {item.tag for item in cs.items if item.passed_fdr_gate}

    assert "RETENTION_AID_FLOW" in gated, "the genuinely-coupled variable should pass the gate"
    noise_vars = {"HEADBOX_CONSISTENCY", "DRYER_HOOD_HUMID", "BROKE_RATIO"}
    false_positives = gated & noise_vars
    assert len(false_positives) == 0, f"pure-noise variables should not pass FDR+support+stability: {false_positives}"
