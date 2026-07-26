"""
drift.py
NFR-M6: "The System MUST monitor input drift (PSI per feature)... Breaching
drift.psi_threshold on any top-10 feature MUST raise a maintenance alert and
annotate the dashboard."
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.config import get_settings


def population_stability_index(reference: np.ndarray, current: np.ndarray, n_bins: int = 10) -> float:
    """Standard PSI: bin the reference distribution into n_bins quantile
    buckets, then compare the current distribution's share in each bucket.
    PSI = sum( (cur_pct - ref_pct) * ln(cur_pct / ref_pct) )."""
    reference = reference[~np.isnan(reference)]
    current = current[~np.isnan(current)]
    if len(reference) < n_bins or len(current) == 0:
        return 0.0

    quantiles = np.linspace(0, 1, n_bins + 1)
    bin_edges = np.unique(np.quantile(reference, quantiles))
    if len(bin_edges) < 3:
        return 0.0

    ref_counts, _ = np.histogram(reference, bins=bin_edges)
    cur_counts, _ = np.histogram(current, bins=bin_edges)
    ref_pct = np.clip(ref_counts / max(len(reference), 1), 1e-4, None)
    cur_pct = np.clip(cur_counts / max(len(current), 1), 1e-4, None)

    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def check_feature_drift(reference_df: pd.DataFrame, current_df: pd.DataFrame,
                         top_features: list[str]) -> dict:
    settings = get_settings()
    results = {}
    breached = []
    for feat in top_features:
        if feat not in reference_df.columns or feat not in current_df.columns:
            continue
        psi = population_stability_index(reference_df[feat].values.astype(float),
                                          current_df[feat].values.astype(float))
        results[feat] = round(psi, 4)
        if psi > settings.drift.psi_threshold:
            breached.append(feat)
    return {"psi_by_feature": results, "breached_features": breached,
            "maintenance_alert": len(breached) > 0}
