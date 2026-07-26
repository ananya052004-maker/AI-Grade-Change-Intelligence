"""
AC-3 (hard gate): 100% of issued recommendations lie within recipe +
actuator + ramp limits; a deliberate limit-violating candidate is provably
suppressed with the binding constraint named.
SAF-01: the safety gate module has zero ML dependency.
"""

import ast
from pathlib import Path

from app.contracts import Constraints, RecipeLimit
from app.recommend.safety_gate import check_candidate, filter_feasible

SAFETY_GATE_PATH = Path(__file__).parent.parent / "app" / "recommend" / "safety_gate.py"

ML_MODULES = {"xgboost", "shap", "sklearn", "scipy", "torch", "tensorflow"}


def test_safety_gate_has_no_ml_imports():
    """SAF-01: 'no ML dependency, so limit enforcement cannot be degraded
    by a model change.' Parses the module's own AST rather than trusting a
    comment -- an import added later would fail this test immediately."""
    tree = ast.parse(SAFETY_GATE_PATH.read_text())
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert imported_roots.isdisjoint(ML_MODULES), f"safety_gate.py imports ML modules: {imported_roots & ML_MODULES}"


def _constraints():
    return Constraints(
        recipe_limits=[RecipeLimit(grade_id="GradeD", variable="BW_MEAS", setpoint=110,
                                    lo_spec=107.25, hi_spec=112.75, lo_alarm=105.6, hi_alarm=114.4,
                                    ramp_rate_max=5.5, source="RECIPE")],
        actuator_ranges={"STOCK_FLOW": [60, 160], "MACHINE_SPEED": [600, 1200]},
        ramp_limits={"STOCK_FLOW": 3.0, "MACHINE_SPEED": 10.0},
    )


def test_within_limits_is_feasible():
    c = check_candidate("STOCK_FLOW", 100, 102, dt_s=5, constraints=_constraints())
    assert c.feasible
    assert c.binding_constraint is None


def test_actuator_range_violation_is_suppressed_not_clipped():
    """FR-14: 'Silent clipping is prohibited.' The candidate must come back
    with to_value == the ORIGINAL out-of-range proposal (200), never a value
    quietly clamped to 160."""
    c = check_candidate("STOCK_FLOW", 150, 200, dt_s=5, constraints=_constraints())
    assert c.feasible is False
    assert c.to_value == 200  # not silently clipped to 160
    assert "actuator_range" in c.binding_constraint


def test_ramp_rate_violation_is_suppressed():
    # 150 -> 300 over 5s = 30/s, way past the 3.0/s limit, but within
    # the actuator's physical range -- isolates the ramp-rate check.
    c = check_candidate("STOCK_FLOW", 150, 155.1, dt_s=0.1, constraints=_constraints())
    assert c.feasible is False
    assert "ramp_rate_max" in c.binding_constraint


def test_recipe_alarm_band_violation_is_suppressed():
    c = check_candidate("BW_MEAS", 110, 130, dt_s=5, constraints=_constraints())
    assert c.feasible is False
    assert "recipe_alarm_band" in c.binding_constraint


def test_filter_feasible_never_drops_suppressed_candidates():
    """FR-14: suppressed candidates must be surfaced with their binding
    constraint, not silently dropped -- filter_feasible returns both lists."""
    constraints = _constraints()
    candidates = [
        check_candidate("STOCK_FLOW", 100, 102, dt_s=5, constraints=constraints),
        check_candidate("STOCK_FLOW", 150, 200, dt_s=5, constraints=constraints),
    ]
    feasible, suppressed = filter_feasible(candidates)
    assert len(feasible) == 1
    assert len(suppressed) == 1
    assert suppressed[0].binding_constraint is not None
