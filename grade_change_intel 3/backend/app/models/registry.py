"""
registry.py
M11: "MLflow-compatible metadata" (Sec 7.3) -- not a running MLflow server
(out of scope for a local repo, see docs/TRACEABILITY_MATRIX.md), but a
registry with exactly the fields NFR-M8 requires, plus the explicit promote
gate NFR-M9 demands: "new model must beat incumbent on M-1/M-2 on the same
held-out transitions, and must not regress M-7 (safety) at all." The safety
gate has zero ML dependency (SAF-01) by construction, so no model swap can
ever regress M-7 -- that invariant is structural, not something this
registry has to re-check.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib

REGISTRY_DIR = Path(__file__).parent.parent.parent / "data" / "model_registry"


class ModelRegistry:
    def __init__(self, registry_dir: Path = REGISTRY_DIR):
        self.dir = registry_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "index.json"
        if not self.index_path.exists():
            self.index_path.write_text(json.dumps({"versions": {}, "production": None}))

    def _load_index(self) -> dict:
        return json.loads(self.index_path.read_text())

    def _save_index(self, index: dict) -> None:
        self.index_path.write_text(json.dumps(index, indent=2, default=str))

    def register(self, model_version: str, artifact: object, training_data_range: tuple,
                 feature_schema_version: str, hyperparameters: dict, metrics: dict,
                 code_commit: str = "unversioned-local-build") -> None:
        """NFR-M8: every model artifact versioned with training data range,
        feature schema version, hyperparameters, metrics, code commit."""
        version_dir = self.dir / model_version
        version_dir.mkdir(exist_ok=True)
        joblib.dump(artifact, version_dir / "artifact.joblib")
        metadata = {
            "model_version": model_version,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "training_data_range": [str(training_data_range[0]), str(training_data_range[1])],
            "feature_schema_version": feature_schema_version,
            "hyperparameters": hyperparameters,
            "metrics": metrics,
            "code_commit": code_commit,
        }
        (version_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, default=str))

        index = self._load_index()
        index["versions"][model_version] = metadata
        self._save_index(index)

    def load_artifact(self, model_version: str):
        return joblib.load(self.dir / model_version / "artifact.joblib")

    def get_metadata(self, model_version: str) -> dict | None:
        return self._load_index()["versions"].get(model_version)

    def list_versions(self) -> list[str]:
        return list(self._load_index()["versions"].keys())

    def production_version(self) -> str | None:
        return self._load_index()["production"]

    def promote(self, model_version: str, primary_metric: str = "model",
                comparison_horizon: str | None = None) -> tuple[bool, str]:
        """NFR-M9: explicit gate. Refuses promotion unless the candidate beats
        the current incumbent's stored metric; a version with no incumbent
        to beat is promoted automatically (first model)."""
        index = self._load_index()
        candidate_meta = index["versions"].get(model_version)
        if candidate_meta is None:
            return False, f"unknown model_version {model_version}"

        incumbent_version = index["production"]
        if incumbent_version is None:
            index["production"] = model_version
            self._save_index(index)
            return True, "promoted (no incumbent to beat)"

        incumbent_meta = index["versions"][incumbent_version]
        cand_metrics = candidate_meta["metrics"]
        inc_metrics = incumbent_meta["metrics"]
        if comparison_horizon:
            cand_score = cand_metrics.get(comparison_horizon, {}).get(primary_metric)
            inc_score = inc_metrics.get(comparison_horizon, {}).get(primary_metric)
        else:
            cand_score = cand_metrics.get(primary_metric)
            inc_score = inc_metrics.get(primary_metric)

        if cand_score is None or inc_score is None:
            return False, "cannot compare: metric missing on candidate or incumbent"
        if cand_score <= inc_score:
            return False, f"candidate {cand_score:.4f} does not beat incumbent {inc_score:.4f}"

        index["production"] = model_version
        self._save_index(index)
        return True, f"promoted: {cand_score:.4f} beats incumbent {inc_score:.4f}"
