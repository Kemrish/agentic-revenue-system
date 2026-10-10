from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class TrackingResult:
    stalled: bool
    reason: str


def check_stall(stage: str, updated_at: datetime, sla_days: int) -> TrackingResult:
    deadline = updated_at + timedelta(days=sla_days)
    stalled = datetime.now(timezone.utc) > deadline
    return TrackingResult(stalled, f"{stage} exceeded {sla_days}-day SLA" if stalled else "within SLA")

