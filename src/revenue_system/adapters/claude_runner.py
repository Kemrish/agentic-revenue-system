"""Claude Agent SDK boundary.

The SDK is imported lazily so replay/test modes do not require credentials or a
live Claude runtime. The application only depends on the AgentRunner protocol.
"""

from typing import TypeVar

from pydantic import BaseModel

from revenue_system.agents.base import AgentRequest

T = TypeVar("T", bound=BaseModel)


class ClaudeRunner:
    def __init__(self, model: str | None = None) -> None:
        self.model = model

    async def run(self, request: AgentRequest, output_type: type[T]) -> T:
        try:
            from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("claude-agent-sdk is required for live Claude mode") from exc
        options = ClaudeAgentOptions(
            model=self.model,
            max_turns=1,
            permission_mode="dontAsk",
            allowed_tools=[],
        )
        async with ClaudeSDKClient(options=options) as client:
            await client.query(request.task)
            result_text: str | None = None
            async for message in client.receive_response():
                if isinstance(message, ResultMessage):
                    result_text = message.result
            if not result_text:
                raise RuntimeError("Claude returned no result")
            if result_text.startswith("Not logged in"):
                raise RuntimeError("Claude CLI is not authenticated. Run `claude /login` or the supported Claude CLI login flow before using live mode.")
        try:
            import json
            candidate = result_text.strip()
            if candidate.startswith("```"):
                candidate = candidate.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                start, end = candidate.find("{"), candidate.rfind("}")
                if start < 0 or end <= start:
                    raise
                payload = json.loads(candidate[start:end + 1])
            return output_type.model_validate(payload)
        except Exception as exc:
            raise ValueError(f"Claude output was not valid {output_type.__name__} JSON") from exc

