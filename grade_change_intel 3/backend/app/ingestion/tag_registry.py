"""
tag_registry.py
DR-02: tag mapping lives in a single declarative config (config/tags.yaml).
No tag name may be hard-coded in application logic -- every module that
needs to know a tag's unit, physical range, or class asks this registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.config import get_tag_registry_raw


@dataclass(frozen=True)
class TagDef:
    site_tag: str
    canonical: str
    unit: str
    tag_class: str
    range: Optional[tuple]


class TagRegistry:
    def __init__(self):
        raw = get_tag_registry_raw()
        self._by_canonical: dict[str, TagDef] = {}
        for t in raw["tags"]:
            rng = tuple(t["range"]) if t.get("range") else None
            self._by_canonical[t["canonical"]] = TagDef(
                site_tag=t["site_tag"], canonical=t["canonical"], unit=t["unit"],
                tag_class=t["class"], range=rng,
            )
        self.required_for_assessment: list[str] = raw["required_for_assessment"]

    def get(self, canonical: str) -> Optional[TagDef]:
        return self._by_canonical.get(canonical)

    def unit_of(self, canonical: str) -> Optional[str]:
        d = self.get(canonical)
        return d.unit if d else None

    def range_of(self, canonical: str) -> Optional[tuple]:
        d = self.get(canonical)
        return d.range if d else None

    def is_scanner_tag(self, canonical: str) -> bool:
        d = self.get(canonical)
        return d is not None and d.tag_class == "primary_quality"

    def all_canonical(self) -> list[str]:
        return list(self._by_canonical.keys())

    def validate_unit(self, canonical: str, unit: str) -> bool:
        """E-05: unit mismatch is a startup failure, not a runtime surprise."""
        expected = self.unit_of(canonical)
        return expected is None or expected == unit

    def check_required_tags(self, present_tags: set) -> tuple[bool, list[str]]:
        """DR-01: refuse to start a transition assessment when any primary
        quality or manipulated tag is missing; say which."""
        missing = [t for t in self.required_for_assessment if t not in present_tags]
        return (len(missing) == 0, missing)


_registry: Optional[TagRegistry] = None


def get_tag_registry() -> TagRegistry:
    global _registry
    if _registry is None:
        _registry = TagRegistry()
    return _registry
