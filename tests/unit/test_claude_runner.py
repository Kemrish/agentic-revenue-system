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

