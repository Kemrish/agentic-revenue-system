"""Typed internal webhook contracts; vendor gateways normalize into these shapes."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InboundModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True, allow_inf_nan=False)


class LeadInput(InboundModel):
    lead_id: str = Field(min_length=1, max_length=200)
    segment: str = Field(min_length=1, max_length=100)
    company_name: str = Field(min_length=1, max_length=300)
    contact_name: str = Field(min_length=1, max_length=300)
    fit: float = Field(default=0, ge=0, le=100)
    intent: float = Field(default=0, ge=0, le=100)
    engagement: float = Field(default=0, ge=0, le=100)


class ReplyInput(InboundModel):
    deal_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200000)


class TranscriptInput(InboundModel):
    deal_id: str = Field(min_length=1, max_length=200)
    transcript: str = Field(min_length=1, max_length=500000)
    deal_terms: dict[str, Any] = Field(default_factory=dict)


class SignatureInput(InboundModel):
    deal_id: str = Field(min_length=1, max_length=200)
    provider_id: str = Field(min_length=1, max_length=300)
