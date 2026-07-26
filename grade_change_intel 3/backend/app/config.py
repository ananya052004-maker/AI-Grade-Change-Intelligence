"""
config.py
Loads config/*.yaml. NFR-9: config over code -- thresholds, tags, and horizons
live in versioned YAML, not as magic numbers scattered through source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).parent.parent / "config"


@dataclass(frozen=True)
class SpecConfig:
    bw_band_pct: float
    persist_scans: int


@dataclass(frozen=True)
class StabConfig:
    band_pct: float
    hold_s: int


@dataclass(frozen=True)
class PredictConfig:
    horizon_s: int
    extra_horizons_s: list
    cycle_s: int


@dataclass(frozen=True)
class SuggestConfig:
    min_interval_s: int
    ttl_s: int
    max_per_set: int


@dataclass(frozen=True)
class CorrelationConfig:
    max_lag_s: int
    fdr_q: float
    min_support_transitions: int


@dataclass(frozen=True)
class DriftConfig:
    psi_threshold: float


@dataclass(frozen=True)
class DataConfig:
    resample_s: int
    max_forward_fill_scans: int
    clock_skew_warn_s: int
    clock_skew_disable_s: int


@dataclass(frozen=True)
class Settings:
    spec: SpecConfig
    stab: StabConfig
    predict: PredictConfig
    risk_thresholds: dict
    suggest: SuggestConfig
    correlation: CorrelationConfig
    drift: DriftConfig
    data: DataConfig
    machine_id: str


@lru_cache
def get_settings() -> Settings:
    raw = yaml.safe_load((CONFIG_DIR / "settings.yaml").read_text())
    return Settings(
        spec=SpecConfig(**raw["spec"]),
        stab=StabConfig(**raw["stab"]),
        predict=PredictConfig(**raw["predict"]),
        risk_thresholds=raw["risk_thresholds"],
        suggest=SuggestConfig(**raw["suggest"]),
        correlation=CorrelationConfig(**raw["correlation"]),
        drift=DriftConfig(**raw["drift"]),
        data=DataConfig(**raw["data"]),
        machine_id=raw["machine_id"],
    )


@lru_cache
def get_tag_registry_raw() -> dict:
    return yaml.safe_load((CONFIG_DIR / "tags.yaml").read_text())


@lru_cache
def get_known_relationships() -> list:
    raw = yaml.safe_load((CONFIG_DIR / "known_relationships.yaml").read_text())
    return raw["known_relationships"]


@lru_cache
def get_actuator_limits() -> dict:
    raw = yaml.safe_load((CONFIG_DIR / "actuator_limits.yaml").read_text())
    return raw["actuator_limits"]
