import asyncio

import pytest

from revenue_system.adapters.claude_runner import ClaudeRunner
from revenue_system.agents.base import AgentRequest, OutreachDraft


@pytest.mark.asyncio
async def test_runner_timeout_is_bounded():
    runner = ClaudeRunner(timeout_seconds=0.001)

    async def slow(*args, **kwargs):
        await asyncio.sleep(1)

    runner._run = slow  # type: ignore[method-assign]
    with pytest.raises(asyncio.TimeoutError):
        await runner.run(AgentRequest("outreach", "test"), OutreachDraft)


@pytest.mark.asyncio
async def test_claude_receives_structured_context(monkeypatch):
    import json
    import sys
    from types import SimpleNamespace

    prompts = []

    class Result:
        result = json.dumps({"subject":"Relevant subject", "body":"Relevant message", "lessons_used":[]})

    async def query(prompt, options):
        prompts.append(prompt)
        yield Result()

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", SimpleNamespace(
        ClaudeAgentOptions=lambda **kw: kw, ResultMessage=Result, query=query))
    result = await ClaudeRunner(api_key="test-only").run(
        AgentRequest("outreach", "Draft outreach", {"company_name":"Evidence Account", "lessons":[{"statement":"Show measured lift"}]}),
        OutreachDraft)
    assert result.subject == "Relevant subject"
    assert "Evidence Account" in prompts[0]
    assert "Show measured lift" in prompts[0]

