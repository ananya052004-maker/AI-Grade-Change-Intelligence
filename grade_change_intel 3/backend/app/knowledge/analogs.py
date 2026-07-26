"""
analogs.py
M5: k-NN historical analog retrieval. Evolves the case-based setpoint
recommendation this session's Streamlit prototype used (and which this same
session already hardened once, biasing toward the fastest-stabilizing half
of matching successes rather than any success) into a component the M6
optimizer treats as its "target" -- FR-21 (show k nearest analogs with
outcomes) and the Sec 6.5 justification for why case-based retrieval beats a
pure black-box optimizer: "this worked before, here's when."
"""

from __future__ import annotations

import pandas as pd

from app.contracts import Analogs
from app.features.feature_engine import MANIPULATED, pivot_wide


class AnalogLibrary:
    def __init__(self, process_timeseries: pd.DataFrame, grade_events: pd.DataFrame):
        self.pt = process_timeseries
        self.events = grade_events

    def find_analogs(self, from_grade: str, to_grade: str, t_sec: float, k: int = 5,
                      window_s: int = 30, prefer_fastest_tercile: bool = True) -> tuple[dict, Analogs]:
        same_pair = self.events[
            (self.events["grade_from"] == from_grade) & (self.events["grade_to"] == to_grade)
            & (self.events["outcome"].isin(["SUCCESS", "DEGRADED"]))
        ]
        pool = same_pair if len(same_pair) >= 3 else self.events[self.events["outcome"].isin(["SUCCESS", "DEGRADED"])]

        # Bias toward the fastest-stabilizing THIRD of the pool (not just any
        # success) so the recommendation actively targets "reduce stabilization
        # time" (M-5/AC-7), not merely reproduce a typical past transition.
        used_fast_bias = False
        if prefer_fastest_tercile and pool["stabilization_time_sec"].notna().sum() >= 3:
            ranked = pool.dropna(subset=["stabilization_time_sec"]).sort_values("stabilization_time_sec")
            n_take = max(3, round(len(ranked) / 3))
            fast_pool = ranked.iloc[:n_take]
            if len(fast_pool) >= 3:
                pool, used_fast_bias = fast_pool, True

        candidate_rows = []
        matched_ids = []
        for _, ev in pool.iterrows():
            wide = pivot_wide(self.pt, ev["transition_id"])
            if wide is None:
                continue
            window = wide[(wide["t_sec"] >= t_sec - window_s) & (wide["t_sec"] <= t_sec + window_s)]
            if window.empty:
                continue
            candidate_rows.append(window[MANIPULATED].median())
            matched_ids.append(ev["transition_id"])

        if not candidate_rows:
            source_tag = "insufficient_historical_matches"
            return {}, Analogs(transition_ids=[], outcomes=[])

        combined = pd.concat(candidate_rows, axis=1).T
        recommended = combined.median().to_dict()
        top_k_ids = matched_ids[:k]
        outcomes = pool[pool["transition_id"].isin(top_k_ids)]["outcome"].tolist()

        source_tag = (
            f"historical_data:successful_{from_grade}_to_{to_grade}_transitions"
            if len(same_pair) >= 3 else "historical_data:similar_grade_transitions"
        )
        if used_fast_bias:
            source_tag += "_fastest_stabilizing_tercile"

        recommended["_source"] = source_tag
        recommended["_based_on_n_events"] = len(candidate_rows)
        recommended["_expected_stabilization_time_sec"] = float(pool["stabilization_time_sec"].median()) if pool["stabilization_time_sec"].notna().any() else None

        return recommended, Analogs(transition_ids=matched_ids[:k], outcomes=outcomes)
