"""
calibration.py
NFR-M5: "Predicted probabilities MUST be calibrated (isotonic or Platt) on a
held-out set; reliability curve and Brier score MUST be reported. Risk
thresholds in FR-08 are only meaningful on calibrated probabilities."
"""

from __future__ import annotations

import numpy as np
from sklearn.isotonic import IsotonicRegression


class IsotonicCalibrator:
    def __init__(self):
        self._iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self._fitted = False

    def fit(self, raw_probs: np.ndarray, y_true: np.ndarray) -> "IsotonicCalibrator":
        self._iso.fit(raw_probs, y_true)
        self._fitted = True
        return self

    def transform(self, raw_probs: np.ndarray) -> np.ndarray:
        if not self._fitted:
            return raw_probs
        return self._iso.predict(raw_probs)
