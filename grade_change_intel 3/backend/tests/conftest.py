import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.orchestrator import GCIOrchestrator
from app.simulation.physics_simulator import GRADES, generate_dataset


@pytest.fixture(scope="session")
def dataset(tmp_path_factory):
    """A small, fast, deterministic dataset dedicated to tests -- separate
    from the demo data/ directory so test runs never depend on (or mutate)
    whatever the dashboard happens to have generated."""
    out_dir = tmp_path_factory.mktemp("gci_test_data")
    return generate_dataset(n_transitions=40, seed=7, machine_id="PM1"), out_dir


@pytest.fixture(scope="session")
def trained_orchestrator():
    """Trains once per test session against the real data/ directory (already
    populated by the app) -- reused across tests that need a full working
    system rather than re-training per test."""
    orch = GCIOrchestrator()
    orch.train()
    return orch


@pytest.fixture
def grade_targets():
    return {g: v["target_bw"] for g, v in GRADES.items()}
