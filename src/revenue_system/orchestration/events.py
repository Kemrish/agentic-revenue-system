from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    event_id: str
    payload: dict[str, Any] = field(default_factory=dict)

