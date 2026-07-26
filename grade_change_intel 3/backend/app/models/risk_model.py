"""
risk_model.py
M3: multi-horizon (60/180/300s) off-spec risk classifier. XGBoost was chosen
over a deep model specifically because FR-18/FR-20 require real per-
prediction explainability -- SHAP gives that for a tree model essentially
for free (this was the correctness-preserving design choice carried over
from the original Streamlit prototype in this session, now hardened with
the validation protocol NFR-M1..M5 that prototype didn't have).
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import shap
import xgboost as xgb

from app.config import get_settings
from app.contracts import Attribution, RiskAssessment, RiskState
from app.features.feature_engine import build_event_features, feature_columns
from app.models.baselines import all_baselines
from app.models.calibration import IsotonicCalibrator
from app.models.evaluation import evaluate_against_baselines, grouped_time_ordered_split, reliability_report

# M-3 (lead time) requires the model to warn AHEAD of an event, not detect it
# concurrently. consecutive_off_spec_scans literally counts scans that are
# ALREADY off-spec right now -- by the time it's informative, the deviation
# is already visible to an operator watching the trend line, so it drives
# PR-AUC up while quietly destroying real lead time. Excluded from the risk
# model's own feature set (still computed and available to other consumers,
# e.g. the Copilot's "why is this risky" answer, which legitimately wants to
# describe the CURRENT state, not just what's genuinely predictive of the future).
CONCURRENT_LEAKY_FEATURES = {"consecutive_off_spec_scans"}


def build_training_table(process_timeseries: pd.DataFrame, grade_events: pd.DataFrame,
                          grade_targets: dict) -> pd.DataFrame:
    """Vectorized feature table across every transition (M2 -> M3 edge)."""
    frames = []
    for _, ev in grade_events.iterrows():
        final_target = grade_targets[ev["grade_to"]]
        wide = build_event_features(process_timeseries, ev["transition_id"], final_target)
        if wide is not None:
            wide["grade_from"] = ev["grade_from"]
            wide["grade_to"] = ev["grade_to"]
            frames.append(wide)
    return pd.concat(frames, ignore_index=True)


def build_horizon_label(table: pd.DataFrame, horizon_scans: int) -> pd.Series:
    """NFR-M1: y=1 iff a sustained off-spec event BEGINS in (t, t+H]. Single
    deterministic function shared by training and evaluation."""
    return (
        table.groupby("event_id")["sustained_off_spec"]
        .transform(lambda s: s.shift(-1).rolling(horizon_scans, min_periods=1).max().fillna(0))
        .astype(int)
    )


class RiskModel:
    def __init__(self, model_version: str | None = None):
        self.settings = get_settings()
        self.horizons_s = sorted(set([self.settings.predict.horizon_s] + self.settings.predict.extra_horizons_s))
        self.default_horizon_s = self.settings.predict.horizon_s
        self.models: dict[int, xgb.XGBClassifier] = {}
        self.calibrators: dict[int, IsotonicCalibrator] = {}
        self.explainers: dict[int, "shap.TreeExplainer"] = {}
        self.feature_cols = [c for c in feature_columns() if c not in CONCURRENT_LEAKY_FEATURES]
        self.seen_grade_pairs: set[tuple] = set()
        self.model_version = model_version or f"risk-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
        self.training_report: dict = {}

    def fit(self, process_timeseries: pd.DataFrame, grade_events: pd.DataFrame, grade_targets: dict) -> dict:
        table = build_training_table(process_timeseries, grade_events, grade_targets)
        table = table[table["event_id"].isin(grade_events[grade_events["outcome"] != "REVERSED"]["transition_id"])]
        self.seen_grade_pairs = set(zip(table["grade_from"], table["grade_to"]))

        train_ids, calib_ids, test_ids = grouped_time_ordered_split(grade_events, train_frac=0.6, calib_frac=0.15)
        dt_s = self.settings.data.resample_s

        for horizon_s in self.horizons_s:
            horizon_scans = max(horizon_s // dt_s, 1)
            y = build_horizon_label(table, horizon_scans)
            X = table[self.feature_cols].fillna(0)

            tr_mask = table["event_id"].isin(train_ids)
            cal_mask = table["event_id"].isin(calib_ids)
            te_mask = table["event_id"].isin(test_ids)

            Xtr, ytr = X[tr_mask], y[tr_mask]
            Xcal, ycal = X[cal_mask], y[cal_mask]
            Xte, yte = X[te_mask], y[te_mask]

            # NFR-M4: class imbalance via weighting; primary metric PR-AUC (evaluation.py).
            pos, neg = max(ytr.sum(), 1), max((ytr == 0).sum(), 1)
            model = xgb.XGBClassifier(
                n_estimators=150, max_depth=4, learning_rate=0.08,
                subsample=0.85, colsample_bytree=0.85, eval_metric="logloss",
                scale_pos_weight=neg / pos, random_state=42,
            )
            model.fit(Xtr, ytr)

            calibrator = IsotonicCalibrator().fit(model.predict_proba(Xcal)[:, 1], ycal)
            calibrated_test = calibrator.transform(model.predict_proba(Xte)[:, 1])

            baselines = all_baselines(table[te_mask], horizon_scans, dt_s, self.settings.spec.bw_band_pct)
            eval_result = evaluate_against_baselines(yte.values, calibrated_test, baselines)
            reliability = reliability_report(yte.values, calibrated_test)

            self.models[horizon_s] = model
            self.calibrators[horizon_s] = calibrator
            self.explainers[horizon_s] = shap.TreeExplainer(model)
            self.training_report[horizon_s] = {
                "n_train": int(tr_mask.sum()), "n_calib": int(cal_mask.sum()), "n_test": int(te_mask.sum()),
                "base_rate_train": float(ytr.mean()), "base_rate_test": float(yte.mean()),
                **eval_result, **{"reliability": reliability},
            }

        return self.training_report

    def predict(self, features: dict, grade_from: str, grade_to: str,
                no_prediction_reason: str | None = None) -> RiskAssessment:
        now = datetime.now(timezone.utc)
        if no_prediction_reason:
            return RiskAssessment(transition_id="", ts=now, p_offspec={}, state=RiskState.NO_PREDICTION,
                                   reason=no_prediction_reason, model_version=self.model_version, calibrated=False)

        low_confidence = (grade_from, grade_to) not in self.seen_grade_pairs

        x = pd.DataFrame([{c: features.get(c, 0.0) for c in self.feature_cols}])
        p_offspec = {}
        attribution = []
        for horizon_s in self.horizons_s:
            raw = float(self.models[horizon_s].predict_proba(x)[0, 1])
            calibrated = float(self.calibrators[horizon_s].transform(np.array([raw]))[0])
            p_offspec[str(horizon_s)] = calibrated
            if horizon_s == self.default_horizon_s:
                shap_vals = self.explainers[horizon_s].shap_values(x)[0]
                top5 = sorted(zip(self.feature_cols, shap_vals), key=lambda kv: abs(kv[1]), reverse=True)[:5]
                attribution = [
                    Attribution(feature=f, shap_value=round(float(v), 4),
                                direction="increases risk" if v > 0 else "decreases risk")
                    for f, v in top5
                ]

        default_p = p_offspec[str(self.default_horizon_s)]
        thresholds = self.settings.risk_thresholds
        if default_p >= thresholds["critical"]:
            state = RiskState.CRITICAL
        elif default_p >= thresholds["at_risk"]:
            state = RiskState.AT_RISK
        elif default_p >= thresholds["watch"]:
            state = RiskState.WATCH
        else:
            state = RiskState.OK
        if low_confidence:
            state = RiskState.LOW_CONFIDENCE

        return RiskAssessment(
            transition_id="", ts=now, p_offspec=p_offspec, state=state,
            attribution=attribution, model_version=self.model_version, calibrated=True,
        )
