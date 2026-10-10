import pytest

from revenue_system.adapters.openrouter_runner import OpenRouterRunner
from revenue_system.agents.base import AgentRequest, OutreachDraft


@pytest.mark.asyncio
async def test_openrouter_runner_parses_typed_response(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"subject":"x","body":"y","confidence":1,"lessons_used":[]}'}}]}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr("httpx.AsyncClient", Client)
    result = await OpenRouterRunner("key").run(AgentRequest("outreach", "draft"), OutreachDraft)
    assert result.subject == "x"

