"""
NFR-7: "identical replay input + identical model version => byte-identical
suggestions." AC-12: full replay of a held-out transition reproduces
byte-identical suggestions on a second run.
"""

import pandas as pd

from app.models.risk_model import RiskModel
from app.simulation.physics_simulator import GRADES, generate_dataset


def test_simulator_is_deterministic_given_the_same_seed(tmp_path):
    """DR-11 / NFR-14: same seed -> byte-identical synthetic dataset."""
    import shutil
    from pathlib import Path

    import app.simulation.physics_simulator as sim_module

    original_out_dir = sim_module.OUT_DIR
    try:
        dir_a, dir_b = tmp_path / "a", tmp_path / "b"
        for d in (dir_a, dir_b):
            sim_module.OUT_DIR = d
            d.mkdir()
            generate_dataset(n_transitions=10, seed=99, machine_id="PM1")

        pt_a = pd.read_parquet(dir_a / "process_timeseries.parquet")
        pt_b = pd.read_parquet(dir_b / "process_timeseries.parquet")
        pd.testing.assert_frame_equal(pt_a, pt_b)

        ge_a = pd.read_parquet(dir_a / "grade_events.parquet")
        ge_b = pd.read_parquet(dir_b / "grade_events.parquet")
        pd.testing.assert_frame_equal(ge_a, ge_b)
    finally:
        sim_module.OUT_DIR = original_out_dir
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_risk_model_predictions_are_deterministic(trained_orchestrator):
    """Two independently-fit RiskModel instances on identical data with the
    same random_state must produce byte-identical predictions for the same
    input row -- otherwise 'model_version' would not be a meaningful audit key."""
    orch = trained_orchestrator
    grade_targets = {g: v["target_bw"] for g, v in GRADES.items()}

    model_a = RiskModel(model_version="determinism-test-a")
    model_a.fit(orch.pt, orch.ge, grade_targets)
    model_b = RiskModel(model_version="determinism-test-b")
    model_b.fit(orch.pt, orch.ge, grade_targets)

    ev = orch.ge.iloc[10]
    wide = orch.wide_for(ev["transition_id"])
    row = wide.iloc[len(wide) // 2]
    from app.features.feature_engine import feature_columns
    feats = {c: row[c] for c in feature_columns() if c in row.index and pd.notna(row[c])}

    risk_a = model_a.predict(feats, ev["grade_from"], ev["grade_to"])
    risk_b = model_b.predict(feats, ev["grade_from"], ev["grade_to"])

    assert risk_a.p_offspec == risk_b.p_offspec, "identical training data + seed must yield identical probabilities"
    assert risk_a.state == risk_b.state
