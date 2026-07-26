"""
trajectory_model.py
FR-06: point forecast trajectory BW_hat(t+1..t+H) with a prediction interval
(P10/P50/P90). Sec 7.3's justification: "physics gives extrapolation safety
outside the training envelope; ML corrects the residual" -- a pure ML
regressor can extrapolate nonsensically on a grade pair with thin data; a
pure physics projection ignores everything the data knows about how THIS
mill's transitions actually behave. This does both:

  1. Physics prior: continue the current FOPDT-style approach-to-target
     using the transition's own recent BW rate of decay toward BW_SP,
     projected forward with no informaton beyond what's already observed.
  2. Residual quantile correction: a small GBM per lead time, per quantile,
     trained to predict (actual - physics_prior) from current features.
     Only the residual has to be learned, which is a much easier regression
     target than raw BW.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import xgboost as xgb

from app.config import get_settings
from app.contracts import Trajectory
from app.features.feature_engine import feature_columns
from app.models.risk_model import build_training_table

LEAD_TIMES_S = [30, 60, 90, 120, 150, 180]
QUANTILES = {"p10": 0.10, "p50": 0.50, "p90": 0.90}


def physics_prior(bw_now, bw_sp_now, roc_now, lead_s: float, tau_s: float = 40.0):
    """First-order approach-to-setpoint projection using the transition's own
    currently-observed closing rate -- no future information used. Works
    elementwise for both scalars and numpy arrays."""
    gap = np.asarray(bw_sp_now) - np.asarray(bw_now)
    decay = np.exp(-lead_s / tau_s)
    at_setpoint = bw_now + roc_now * lead_s * decay          # gap ~ 0: extrapolate current trend
    approaching = bw_sp_now - gap * decay                     # else: decay toward setpoint
    result = np.where(np.abs(gap) < 1e-6, at_setpoint, approaching)
    return result if np.ndim(result) else float(result)


def _future_bw(table: pd.DataFrame, lead_scans: int) -> pd.Series:
    return table.groupby("event_id")["BW_MEAS"].shift(-lead_scans)


class TrajectoryModel:
    def __init__(self, model_version: str | None = None):
        self.settings = get_settings()
        self.feature_cols = feature_columns()
        self.models: dict[tuple[int, str], GradientBoostingRegressor] = {}
        self.model_version = model_version or "trajectory-dev"

    def fit(self, process_timeseries: pd.DataFrame, grade_events: pd.DataFrame, grade_targets: dict) -> dict:
        table = build_training_table(process_timeseries, grade_events, grade_targets)
        table = table[table["event_id"].isin(grade_events[grade_events["outcome"] != "REVERSED"]["transition_id"])]
        dt_s = self.settings.data.resample_s

        report = {}
        for lead_s in LEAD_TIMES_S:
            lead_scans = max(int(round(lead_s / dt_s)), 1)
            future_bw = _future_bw(table, lead_scans)
            prior = physics_prior(table["BW_MEAS"].values, table["BW_SP"].values,
                                   table["BW_MEAS_roc"].values, lead_s)
            residual = future_bw - prior
            valid = residual.notna()

            X = table.loc[valid, self.feature_cols].fillna(0)
            y = residual[valid]
            for qname, q in QUANTILES.items():
                model = xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=q,
                                          n_estimators=80, max_depth=3, learning_rate=0.08, random_state=42)
                model.fit(X, y)
                self.models[(lead_s, qname)] = model
            report[lead_s] = {"n_train": int(valid.sum())}
        return report

    def predict(self, features: dict, bw_now: float, bw_sp_now: float, roc_now: float) -> Trajectory:
        x = pd.DataFrame([{c: features.get(c, 0.0) for c in self.feature_cols}])
        t_s, p10, p50, p90 = [], [], [], []
        for lead_s in LEAD_TIMES_S:
            prior = physics_prior(bw_now, bw_sp_now, roc_now, lead_s)
            vals = {}
            for qname in QUANTILES:
                residual = float(self.models[(lead_s, qname)].predict(x)[0])
                vals[qname] = prior + residual
            # enforce monotonic P10 <= P50 <= P90 regardless of independent quantile fits
            ordered = sorted(vals.values())
            t_s.append(lead_s)
            p10.append(ordered[0])
            p50.append(ordered[1])
            p90.append(ordered[2])
        return Trajectory(t_s=t_s, p10=p10, p50=p50, p90=p90)
