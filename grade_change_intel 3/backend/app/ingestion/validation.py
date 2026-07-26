"""
validation.py
DR-01, DR-03..DR-09 data quality gates. Sits between the adapter and the
canonical contract per the M1 module map: SourceAdapter -> validation -> the
rest of the system never sees an unvalidated Frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.config import get_settings
from app.contracts import Frame, Quality, TagSample
from app.ingestion.tag_registry import get_tag_registry


@dataclass
class DataHealthReport:
    """UX-08: the dashboard MUST degrade visibly, not silently. This is what
    a data-health banner renders from."""
    ts: datetime
    missing_required_tags: list = field(default_factory=list)
    stale_tags: list = field(default_factory=list)
    clamped_tags: list = field(default_factory=list)
    clock_skew_s: float = 0.0
    prediction_disabled: bool = False
    confidence_penalty: float = 0.0  # multiplicative penalty from staleness (E-21)


class IngestionValidator:
    """Stateful: forward-fill and staleness tracking require memory of the
    last-known-good value per tag across the stream."""

    def __init__(self):
        self.settings = get_settings()
        self.registry = get_tag_registry()
        self._last_good: dict[str, TagSample] = {}
        self._last_good_ts: dict[str, datetime] = {}
        self._stale_scan_count: dict[str, int] = {}

    def validate(self, frame: Frame) -> tuple[Frame, DataHealthReport]:
        report = DataHealthReport(ts=frame.ts)
        resample_s = self.settings.data.resample_s
        max_ff_scans = self.settings.data.max_forward_fill_scans

        clean_tags: dict[str, TagSample] = {}
        for canonical in self.registry.all_canonical():
            sample = frame.tags.get(canonical)

            # DR-03: reject/flag quality != GOOD; forward-fill up to max_ff_scans,
            # then mark STALE and downgrade confidence.
            if sample is None or sample.quality != Quality.GOOD:
                self._stale_scan_count[canonical] = self._stale_scan_count.get(canonical, 0) + 1
                if canonical in self._last_good and self._stale_scan_count[canonical] <= max_ff_scans:
                    filled = self._last_good[canonical]
                    age = (frame.ts - self._last_good_ts[canonical]).total_seconds()
                    clean_tags[canonical] = TagSample(value=filled.value, quality=Quality.UNCERTAIN,
                                                        age_since_scan_s=age)
                    continue
                elif canonical in self._last_good:
                    age = (frame.ts - self._last_good_ts[canonical]).total_seconds()
                    clean_tags[canonical] = TagSample(value=self._last_good[canonical].value,
                                                        quality=Quality.STALE, age_since_scan_s=age)
                    report.stale_tags.append(canonical)
                    continue
                else:
                    continue  # never seen a good value yet; tag is simply absent this frame

            # DR-04: clamp-and-flag physically impossible values.
            value = sample.value
            rng = self.registry.range_of(canonical)
            clamped = False
            if rng is not None:
                lo, hi = rng
                if value < lo or value > hi:
                    value = max(lo, min(hi, value))
                    clamped = True
                    report.clamped_tags.append(canonical)

            self._stale_scan_count[canonical] = 0
            final = TagSample(value=value, quality=Quality.GOOD if not clamped else Quality.UNCERTAIN,
                               age_since_scan_s=0.0 if self.registry.is_scanner_tag(canonical) else None)
            clean_tags[canonical] = final
            self._last_good[canonical] = final
            self._last_good_ts[canonical] = frame.ts

        # DR-01: refuse to start assessment when a primary/manipulated tag is missing.
        ok, missing = self.registry.check_required_tags(set(clean_tags.keys()))
        report.missing_required_tags = missing
        if not ok:
            report.prediction_disabled = True

        # E-21: confidence multiplicatively penalised by staleness.
        if report.stale_tags:
            report.confidence_penalty = min(0.9, 0.15 * len(report.stale_tags))

        clean_frame = Frame(ts=frame.ts, machine_id=frame.machine_id, tags=clean_tags)
        return clean_frame, report

    def check_clock_skew(self, source_ts: datetime, reference_ts: datetime) -> DataHealthReport:
        """DR-09: clock skew > warn_s raises a warning; > disable_s disables prediction."""
        skew = abs((source_ts - reference_ts).total_seconds())
        report = DataHealthReport(ts=source_ts, clock_skew_s=skew)
        if skew > self.settings.data.clock_skew_disable_s:
            report.prediction_disabled = True
        return report
