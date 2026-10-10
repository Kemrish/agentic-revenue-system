import asyncio
import json
from typing import TypeVar

import httpx
from pydantic import BaseModel

from revenue_system.agents.base import AgentRequest

T = TypeVar("T", bound=BaseModel)


class OpenRouterRunner:
    def __init__(self, api_key: str, model: str = "anthropic/claude-3.5-sonnet", timeout_seconds: float = 60.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def run(self, request: AgentRequest, output_type: type[T]) -> T:
        schema = output_type.model_json_schema()
        prompt = f"{request.task}\n\nReturn only JSON matching this schema:\n{json.dumps(schema)}\n\nContext:\n{json.dumps(request.context, default=str)}"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://agentic-revenue-system.local", "X-Title": "Agentic Revenue System"}
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 1200,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": output_type.__name__, "strict": True, "schema": schema},
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await asyncio.wait_for(client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload), timeout=self.timeout_seconds)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        candidate = content.strip()
        if candidate.startswith("```"):
            candidate = candidate.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            start, end = candidate.find("{"), candidate.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("OpenRouter returned no JSON object")
            data = json.loads(candidate[start:end + 1])
        return output_type.model_validate(data)

