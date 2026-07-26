"""
base.py
DR-10: "Live and replay ingestion MUST share one adapter interface
(SourceAdapter.stream(from_ts, to_ts) -> Iterator[Frame]) so the model code
cannot tell the difference." This is the single most important architectural
decision the PRD calls out (A-1..A-5 fallback design), because it's what
makes the whole build safe under real-data uncertainty: everything downstream
of this interface is identical whether the bytes came from a live historian
or a replayed/simulated file.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterator

from app.contracts import Frame


class SourceAdapter(ABC):
    @abstractmethod
    def stream(self, from_ts: datetime, to_ts: datetime) -> Iterator[Frame]:
        """Yield Frame objects in ascending ts order, one per resample tick."""
        raise NotImplementedError

    @abstractmethod
    def drop_tag(self, canonical_tag: str) -> None:
        """Simulate a tag dropout at the adapter boundary (AC-13: the System
        must degrade correctly when a primary tag is removed at runtime)."""
        raise NotImplementedError

    @abstractmethod
    def restore_tag(self, canonical_tag: str) -> None:
        raise NotImplementedError
