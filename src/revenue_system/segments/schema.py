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


def load_pack(path: Path) -> SegmentPack:
    with path.open(encoding="utf-8") as handle:
        return SegmentPack.model_validate(yaml.safe_load(handle))

