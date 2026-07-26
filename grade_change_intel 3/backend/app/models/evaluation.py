"""
evaluation.py
NFR-M2 (non-negotiable): "Splits MUST be grouped by transition_id and
ordered in time (train on older transitions, test on newer). Random
row-level splits leak, because adjacent 5s rows within a transition are
near-identical, and would inflate M-1 to a meaningless number."

This is the single most important correctness fix versus the earlier
Streamlit prototype in this session, which trained and evaluated the risk
model on the exact same rows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss


def grouped_time_ordered_split(events_df: pd.DataFrame, train_frac: float = 0.6,
                                calib_frac: float = 0.15) -> tuple[list, list, list]:
    """Sort transitions by ts_start (oldest first); train on the oldest
    train_frac, calibrate on the next calib_frac, test on the newest
    remainder. Every row of a given transition_id lands on exactly one side
    because the split operates on whole transitions, not rows.
    """
    ordered = events_df.sort_values("ts_start")
    n = len(ordered)
    n_train = int(n * train_frac)
    n_calib = int(n * calib_frac)
    train_ids = ordered.iloc[:n_train]["transition_id"].tolist()
    calib_ids = ordered.iloc[n_train:n_train + n_calib]["transition_id"].tolist()
    test_ids = ordered.iloc[n_train + n_calib:]["transition_id"].tolist()
    return train_ids, calib_ids, test_ids


def pr_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """NFR-M4: primary reported metric is PR-AUC, not ROC-AUC/accuracy,
    because off-spec events are the minority class."""
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(average_precision_score(y_true, y_score))


def evaluate_against_baselines(y_true: np.ndarray, model_score: np.ndarray, baselines: dict) -> dict:
    """AC-2: model must beat all three naive baselines on PR-AUC."""
    result = {"model": pr_auc(y_true, model_score)}
    for name, pred in baselines.items():
        result[f"baseline__{name}"] = pr_auc(y_true, pred)
    result["beats_all_baselines"] = all(
        result["model"] > v for k, v in result.items() if k.startswith("baseline__") and not np.isnan(v)
    )
    return result


def reliability_report(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> dict:
    """NFR-M5: reliability curve + Brier score must be reported for
    calibrated probabilities."""
    from sklearn.calibration import calibration_curve
    brier = float(brier_score_loss(y_true, y_prob))
    if len(np.unique(y_true)) < 2:
        return {"brier_score": brier, "bin_true": [], "bin_pred": []}
    frac_pos, mean_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy="quantile")
    return {"brier_score": brier, "bin_true": frac_pos.tolist(), "bin_pred": mean_pred.tolist()}
