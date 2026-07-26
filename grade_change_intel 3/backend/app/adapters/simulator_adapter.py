"""
simulator_adapter.py
DR-10: the simulator is a SourceAdapter too, behind the identical interface.
In practice its output IS replay data (physics_simulator writes the same
canonical parquet ReplayAdapter reads), so this adapter's only job is to
(re)generate that data on demand and then delegate -- proving the "one
adapter interface" claim rather than just asserting it.
"""

from __future__ import annotations

from pathlib import Path

from app.adapters.replay_adapter import ReplayAdapter, DATA_DIR
from app.simulation.physics_simulator import generate_dataset


class SimulatorAdapter(ReplayAdapter):
    def __init__(self, machine_id: str = "PM1", n_transitions: int = 160, seed: int = 42,
                 data_dir: Path = DATA_DIR, force_regenerate: bool = False):
        if force_regenerate or not (data_dir / "process_timeseries.parquet").exists():
            generate_dataset(n_transitions=n_transitions, seed=seed, machine_id=machine_id)
        super().__init__(machine_id=machine_id, data_dir=data_dir)
