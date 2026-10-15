from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class Tier(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class ActionType(StrEnum):
    ENRICH = "enrich"
    SCORE = "score"
    SEND_FIRST_TOUCH = "send_first_touch"
    SEND_FOLLOW_UP = "send_follow_up"
    CHANGE_PRICING = "change_pricing"
    GENERATE_IO = "generate_io"
    SEND_CONTRACT = "send_contract"
    SYNC_CRM = "sync_crm"


@dataclass
class Score:
    fit: float
    intent: float
    engagement: float
    total: float
    tier: Tier
    reason: str
    fired_rules: list[str] = field(default_factory=list)


@dataclass
class Deal:
    id: str
    segment: str
    company_name: str
    contact_name: str
    stage: str = "new"
    fields: dict[str, Any] = field(default_factory=dict)
    score: Score | None = None
    flags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class Action:
    action_type: ActionType
    deal_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    reason: str
    rule_id: str

