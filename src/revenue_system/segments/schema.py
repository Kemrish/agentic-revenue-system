from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class ScoringConfig(BaseModel):
    weights: dict[str, float]
    tiers: dict[str, int]
    fit_gate_for_a: int = 40

    @field_validator("weights")
    @classmethod
    def weights_sum_to_one(cls, value: dict[str, float]) -> dict[str, float]:
        if abs(sum(value.values()) - 1.0) > 0.001:
            raise ValueError("scoring weights must sum to 1")
        return value


class TemplateConfig(BaseModel):
    first_touch: str
    follow_up: str
    contract: str


class SegmentPack(BaseModel):
    segment: str
    display_name: str
    scoring: ScoringConfig
    qualification_fields: list[str] = Field(default_factory=list)
    messaging: dict[str, Any] = Field(default_factory=dict)
    templates: TemplateConfig
    autonomy: dict[str, list[str]] = Field(default_factory=dict)
    sla_days: dict[str, int] = Field(default_factory=dict)
    follow_up_limit: int = Field(default=2, ge=0, le=5)

    @field_validator("sla_days")
    @classmethod
    def sla_stages_exist(cls, value: dict[str, int]) -> dict[str, int]:
        from revenue_system.domain.stages import STAGES
        unknown = set(value) - set(STAGES)
        if unknown:
            raise ValueError(f"sla_days names unknown stages: {sorted(unknown)}")
        if any(days <= 0 for days in value.values()):
            raise ValueError("sla_days must be positive")
        return value


def load_pack(path: Path) -> SegmentPack:
    with path.open(encoding="utf-8") as handle:
        return SegmentPack.model_validate(yaml.safe_load(handle))

