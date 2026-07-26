"""
AC-2: model beats all three naive baselines (NFR-M3) on PR-AUC, at every
predicted horizon, on the transition-grouped time-ordered holdout.
"""


def test_risk_model_beats_all_baselines_at_every_horizon(trained_orchestrator):
    report = trained_orchestrator.risk_model.training_report
    assert report, "training report should be populated after .train()"
    for horizon_s, r in report.items():
        assert r["beats_all_baselines"], f"horizon {horizon_s}s: model does not beat all naive baselines"
        assert r["model"] > 0.5, f"horizon {horizon_s}s: PR-AUC suspiciously low ({r['model']})"


def test_risk_model_base_rate_reflects_class_imbalance(trained_orchestrator):
    """NFR-M4 sanity check: off-spec should be the minority class, not ~50%
    (which would suggest the label/split logic is broken)."""
    report = trained_orchestrator.risk_model.training_report
    for horizon_s, r in report.items():
        assert 0.0 < r["base_rate_test"] < 0.5, f"horizon {horizon_s}s base rate {r['base_rate_test']} looks wrong"


def test_train_test_split_is_grouped_by_transition(trained_orchestrator):
    """NFR-M2: no transition_id may appear on both sides of the split."""
    from app.models.evaluation import grouped_time_ordered_split
    train_ids, calib_ids, test_ids = grouped_time_ordered_split(trained_orchestrator.ge, 0.6, 0.15)
    assert set(train_ids).isdisjoint(test_ids)
    assert set(calib_ids).isdisjoint(test_ids)
    assert set(train_ids).isdisjoint(calib_ids)
