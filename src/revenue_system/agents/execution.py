from typing import TypeVar

from pydantic import BaseModel

from .base import AgentRequest, AgentRunner
from .prompts import load_prompt
from .recording import Recording, RecordingStore, request_hash

T = TypeVar("T", bound=BaseModel)


class DisabledRunner:
    async def run(self, request: AgentRequest, output_type: type[T]) -> T:
        raise RuntimeError("Agent execution is disabled; configure RUNTIME_MODE, CLAUDE_MODE, and the live LLM provider")


class ValidatingRunner:
    """Shared execution guard for live and replay runners."""

    def __init__(self, delegate: AgentRunner) -> None:
        self.delegate = delegate

    async def run(self, request: AgentRequest, output_type: type[T]) -> T:
        prompt, version = load_prompt(request.agent_name)
        enriched = AgentRequest(request.agent_name, f"{prompt}\n\n{request.task}", request.context, version)
        result = await self.delegate.run(enriched, output_type)
        return output_type.model_validate(result.model_dump())


class RecordingRunner:
    def __init__(self, delegate: AgentRunner, store: RecordingStore) -> None:
        self.delegate = delegate
        self.store = store

    async def run(self, request: AgentRequest, output_type: type[T]) -> T:
        result = await self.delegate.run(request, output_type)
        self.store.save(Recording(request.agent_name, request.prompt_version, request_hash(request), result.model_dump()))
        return result


class RecordedReplayRunner:
    def __init__(self, store: RecordingStore) -> None:
        self.store = store

    async def run(self, request: AgentRequest, output_type: type[T]) -> T:
        recording = self.store.load(request)
        return output_type.model_validate(recording.output)

