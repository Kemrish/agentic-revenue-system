from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel


class OutreachDraft(BaseModel):
    subject: str
    body: str
    confidence: float = 1.0
    lessons_used: list[str] = []


@dataclass(frozen=True)
class AgentRequest:
    agent_name: str
    task: str
    context: dict[str, Any] = field(default_factory=dict)
    prompt_version: str = "v1"


T = TypeVar("T", bound=BaseModel)


class AgentRunner(Protocol):
    async def run(self, request: AgentRequest, output_type: type[T]) -> T: ...

