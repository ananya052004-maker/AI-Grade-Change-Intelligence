"""
feature_engine.py
M2: transition detection -> phase classification -> dead-time alignment ->
rolling stats/rates/ratios -> constraint proximity -> FeatureVector. This is
the single source of truth every downstream module (M3 risk, M4 correlation,
M6 recommendation) reads from, so all of them see identical engineered
features (PRD Sec "Module Communication" design principle carried over from
this session's original prototype, now formalised as its own module).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.config import get_actuator_limits, get_settings
from app.contracts import FeatureVector, Phase
from app.features.phase import classify_phase_series

FEATURE_SCHEMA_VERSION = "1.0"

MANIPULATED = ["STOCK_FLOW", "FILLER_FLOW", "STEAM_PRESS_G1", "MACHINE_SPEED"]
QUALITY = ["MOIST_MEAS", "ASH_MEAS", "CALIPER_MEAS"]
CONTEXT = ["HEADBOX_CONSISTENCY", "DRYER_HOOD_HUMID", "RETENTION_AID_FLOW", "BROKE_RATIO"]
ALL_NUMERIC = MANIPULATED + QUALITY + CONTEXT + ["BW_MEAS", "BW_SP"]


def pivot_wide(process_timeseries: pd.DataFrame, event_id: str) -> pd.DataFrame | None:
    """Reconstruct the wide per-event table from the canonical long-format
    contract -- BW_MEAS/BW_SP/etc are the single source of truth; nothing is
    read from a separately-cached wide file."""
    sub = process_timeseries[process_timeseries["event_id"] == event_id]
    if sub.empty:
        return None
    wide = sub.pivot_table(index="ts", columns="tag", values="value", aggfunc="last").sort_index()
    wide = wide.reset_index()
    wide["t_sec"] = (wide["ts"] - wide["ts"].iloc[0]).dt.total_seconds()
    return wide


def add_derived_columns(wide: pd.DataFrame, dt_s: int, persist_scans: int, spec_band_pct: float) -> pd.DataFrame:
    wide = wide.copy()
    wide["bw_deviation_pct"] = 100 * (wide["BW_MEAS"] - wide["BW_SP"]) / wide["BW_SP"]
    wide["off_spec"] = wide["bw_deviation_pct"].abs() > spec_band_pct
    wide["sustained_off_spec"] = (
        wide["off_spec"].rolling(persist_scans).apply(lambda w: w.all()).fillna(False).astype(bool)
    )
    # How close the transition already is to a *sustained* excursion right now --
    # directly predictive of the near-term label, and cheap to compute online
    # (a running counter), unlike most of the other engineered features.
    off_spec_int = wide["off_spec"].astype(int)
    reset_groups = (off_spec_int == 0).cumsum()
    wide["consecutive_off_spec_scans"] = off_spec_int.groupby(reset_groups).cumsum()
    wide["bw_deviation_pct_roc"] = wide["bw_deviation_pct"].diff().fillna(0) / dt_s
    for col in ALL_NUMERIC:
        if col in wide.columns:
            wide[f"{col}_roc"] = wide[col].diff().fillna(0) / dt_s
            wide[f"{col}_rollstd"] = wide[col].rolling(4, min_periods=1).std().fillna(0)
    return wide


def add_constraint_proximity(wide: pd.DataFrame) -> pd.DataFrame:
    """M2: distance to actuator limits, normalised 0 (at low limit) .. 1 (at
    high limit) so 'near saturation' is a simple threshold on either tail --
    this is what feeds FR-15 (don't recommend a handle that's already maxed)."""
    wide = wide.copy()
    limits = get_actuator_limits()
    for tag in MANIPULATED:
        if tag not in wide.columns:
            continue
        lo, hi = limits[tag]["lo"], limits[tag]["hi"]
        wide[f"{tag}_prox"] = ((wide[tag] - lo) / (hi - lo)).clip(0, 1)
        wide[f"{tag}_saturated"] = (wide[f"{tag}_prox"] > 0.95) | (wide[f"{tag}_prox"] < 0.05)
    return wide


def add_phase(wide: pd.DataFrame, dt_s: int, final_target: float, band_pct: float) -> pd.DataFrame:
    wide = wide.copy()
    wide["phase"] = classify_phase_series(wide["BW_SP"].values, wide["BW_MEAS"].values, dt_s, final_target, band_pct)
    return wide


PHASE_DUMMIES = [f"phase_{p.value}" for p in Phase]


def add_phase_dummies(wide: pd.DataFrame) -> pd.DataFrame:
    wide = wide.copy()
    for p in Phase:
        wide[f"phase_{p.value}"] = (wide["phase"] == p).astype(float)
    return wide


def feature_columns() -> list[str]:
    cols = ["bw_deviation_pct", "bw_deviation_pct_roc", "consecutive_off_spec_scans"]
    for tag in ALL_NUMERIC:
        cols += [tag, f"{tag}_roc", f"{tag}_rollstd"]
    for tag in MANIPULATED:
        cols += [f"{tag}_prox"]
    cols += PHASE_DUMMIES
    return cols


def build_event_features(process_timeseries: pd.DataFrame, event_id: str, final_target: float) -> pd.DataFrame | None:
    settings = get_settings()
    wide = pivot_wide(process_timeseries, event_id)
    if wide is None:
        return None
    wide = add_derived_columns(wide, settings.data.resample_s, settings.spec.persist_scans, settings.spec.bw_band_pct)
    wide = add_constraint_proximity(wide)
    wide = add_phase(wide, settings.data.resample_s, final_target, settings.stab.band_pct)
    wide = add_phase_dummies(wide)
    wide["event_id"] = event_id
    return wide


def row_to_feature_vector(row: pd.Series, transition_id: str, schema_version: str = FEATURE_SCHEMA_VERSION) -> FeatureVector:
    features = {c: float(row[c]) for c in feature_columns() if c in row.index and pd.notna(row[c])}
    return FeatureVector(
        ts=row["ts"], transition_id=transition_id, phase=Phase(row["phase"]),
        schema_version=schema_version, features=features,
    )
