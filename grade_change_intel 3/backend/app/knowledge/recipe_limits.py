"""
recipe_limits.py
M5: knowledge module. Loads recipe_limits (per-grade spec/alarm bands,
generated alongside the physics simulator's transitions) and actuator
physical ranges/ramp limits (config/actuator_limits.yaml), and assembles
them into the Constraints contract the safety gate (M6/SAF-01) checks
every candidate against.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.config import get_actuator_limits
from app.contracts import Constraints, RecipeLimit

DATA_DIR = Path(__file__).parent.parent.parent / "data"


class RecipeLimitsStore:
    def __init__(self, data_dir: Path = DATA_DIR):
        self._df = pd.read_parquet(data_dir / "recipe_limits.parquet")

    def for_grade(self, grade_id: str) -> list[RecipeLimit]:
        sub = self._df[self._df["grade_id"] == grade_id]
        return [RecipeLimit(**row) for row in sub.to_dict(orient="records")]

    def get(self, grade_id: str, variable: str) -> RecipeLimit | None:
        sub = self._df[(self._df["grade_id"] == grade_id) & (self._df["variable"] == variable)]
        if sub.empty:
            return None
        return RecipeLimit(**sub.iloc[0].to_dict())

    def has_grade(self, grade_id: str) -> bool:
        """E-07: missing recipe entry for the target grade."""
        return grade_id in self._df["grade_id"].unique()

    def constraints_for(self, grade_id: str) -> Constraints:
        limits = get_actuator_limits()
        return Constraints(
            recipe_limits=self.for_grade(grade_id),
            actuator_ranges={tag: [v["lo"], v["hi"]] for tag, v in limits.items()},
            ramp_limits={tag: v["ramp_rate_max_per_s"] for tag, v in limits.items()},
        )
