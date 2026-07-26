"""
E-26: risk-state hysteresis. Doesn't need a trained model -- exercises the
pure state machine directly, so it's fast even though GCIOrchestrator's
constructor touches the data layer.
"""

import pytest

from app.contracts import RiskState
from app.orchestrator import GCIOrchestrator


@pytest.fixture(scope="module")
def orch():
    return GCIOrchestrator()  # constructor only loads data, does not train


def test_single_cycle_downgrade_is_held(orch):
    eid = "TESTEVT-A"
    assert orch._apply_hysteresis(eid, RiskState.CRITICAL) == RiskState.CRITICAL
    # a single lower reading should NOT immediately downgrade the display
    assert orch._apply_hysteresis(eid, RiskState.WATCH) == RiskState.CRITICAL


def test_two_consecutive_lower_cycles_clears_the_band(orch):
    eid = "TESTEVT-B"
    orch._apply_hysteresis(eid, RiskState.CRITICAL)
    orch._apply_hysteresis(eid, RiskState.WATCH)  # held
    result = orch._apply_hysteresis(eid, RiskState.WATCH)  # 2nd consecutive lower reading
    assert result == RiskState.WATCH


def test_upgrade_is_never_delayed(orch):
    eid = "TESTEVT-C"
    orch._apply_hysteresis(eid, RiskState.OK)
    result = orch._apply_hysteresis(eid, RiskState.CRITICAL)
    assert result == RiskState.CRITICAL, "an upgrade toward more severe must never be held back"


def test_no_prediction_passes_through_unaffected(orch):
    eid = "TESTEVT-D"
    orch._apply_hysteresis(eid, RiskState.CRITICAL)
    assert orch._apply_hysteresis(eid, RiskState.NO_PREDICTION) == RiskState.NO_PREDICTION
