"""
replay_adapter.py
CSV/Parquet-backed SourceAdapter with a virtual clock. Serves both:
  - `stream()`: the DR-10 interface, yields as fast as the data can be read
    (used for training, feature building, and the AC-12 replay-determinism
    test -- iterating a 22-minute transition takes milliseconds, i.e. far
    more than the NFR-4 >=100x real-time target).
  - `paced_stream()`: an additional capability (not part of the abstract
    interface) used by the live orchestrator to emit Frames at a wall-clock
    cadence scaled by `speed`, so the WebSocket demo looks "live" without
    needing a real historian.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Iterator

import pandas as pd

from app.adapters.base import SourceAdapter
from app.contracts import Frame, Quality, TagSample

DATA_DIR = Path(__file__).parent.parent.parent / "data"


class ReplayAdapter(SourceAdapter):
    def __init__(self, machine_id: str = "PM1", data_dir: Path = DATA_DIR):
        self.machine_id = machine_id
        self._pt = pd.read_parquet(data_dir / "process_timeseries.parquet")
        self._pt["ts"] = pd.to_datetime(self._pt["ts"], utc=True)
        self._dropped_tags: set[str] = set()

    def drop_tag(self, canonical_tag: str) -> None:
        self._dropped_tags.add(canonical_tag)

    def restore_tag(self, canonical_tag: str) -> None:
        self._dropped_tags.discard(canonical_tag)

    def _frames(self, from_ts: datetime, to_ts: datetime, event_id: str | None = None) -> Iterator[Frame]:
        df = self._pt
        mask = (df["ts"] >= pd.Timestamp(from_ts)) & (df["ts"] <= pd.Timestamp(to_ts))
        if event_id is not None:
            mask &= (df["event_id"] == event_id)
        df = df[mask].sort_values("ts")
        for ts, group in df.groupby("ts", sort=True):
            tags = {}
            for row in group.itertuples(index=False):
                if row.tag in self._dropped_tags:
                    continue
                tags[row.tag] = TagSample(value=float(row.value), quality=Quality(row.quality))
            yield Frame(ts=ts.to_pydatetime(), machine_id=self.machine_id, tags=tags)

    def stream(self, from_ts: datetime, to_ts: datetime) -> Iterator[Frame]:
        yield from self._frames(from_ts, to_ts)

    def stream_event(self, event_id: str) -> Iterator[Frame]:
        """Convenience: replay exactly one transition_id's window, full range."""
        sub = self._pt[self._pt["event_id"] == event_id]
        if sub.empty:
            return
        yield from self._frames(sub["ts"].min(), sub["ts"].max(), event_id=event_id)

    def paced_stream(self, event_id: str, speed: float = 20.0, cycle_s: int = 5) -> Iterator[Frame]:
        """Yield Frames at wall-clock intervals of cycle_s/speed seconds, so a
        22-minute transition plays out over ~66s at speed=20 -- enough to see
        risk state evolve live in a demo without waiting the full duration."""
        delay = cycle_s / speed
        for frame in self.stream_event(event_id):
            yield frame
            time.sleep(delay)

    def known_event_ids(self) -> list[str]:
        return sorted(self._pt["event_id"].unique().tolist())
