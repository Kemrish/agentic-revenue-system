import hashlib
import json
from typing import Any, TypeVar

from pydantic import BaseModel

from .base import AgentRequest, AgentRunner

T = TypeVar("T", bound=BaseModel)


class FakeRunner:
    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self.responses = responses or {}

    async def run(self, request: AgentRequest, output_type: type[T]) -> T:
        response = self.responses.get(request.agent_name)
        if response is None and request.agent_name == "outreach":
            response = {
                "subject": f"A growth idea for {request.context['company_name']}",
                "body": f"Hi {request.context['contact_name']},\n\n{request.context.get('value_proposition', 'I would like to share a relevant idea for your team.')}\n\nBest,\nCool AI",
                "confidence": 0.95,
                "lessons_used": request.context.get("lessons_used", []),
            }
        if response is None:
            raise KeyError(f"No fake response for agent: {request.agent_name}")
        return output_type.model_validate(response)


class ReplayRunner(FakeRunner):
    def __init__(self, recordings: dict[str, dict[str, Any]]) -> None:
        super().__init__(recordings)

    @staticmethod
    def input_hash(request: AgentRequest) -> str:
        encoded = json.dumps(request.context, sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()

