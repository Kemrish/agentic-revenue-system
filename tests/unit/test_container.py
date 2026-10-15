import pytest

from revenue_system.adapters.disabled import DisabledIntegration
from revenue_system.agents.base import AgentRequest, OutreachDraft
from revenue_system.container import agent_runner, build_container
from revenue_system.settings import Settings


@pytest.mark.asyncio
async def test_non_live_container_refuses_side_effects():
    container = build_container(Settings(runtime_mode="test"))
    try:
        assert isinstance(container.mail, DisabledIntegration)
        assert container.crm is None
        with pytest.raises(RuntimeError, match="disabled"):
            await container.mail.send("a@example.com", "Subject", "Body", "id")
        with pytest.raises(RuntimeError, match="disabled"):
            await container.esign.send_for_signature("Agreement", "id")
        with pytest.raises(RuntimeError, match="disabled"):
            await container.runner.run(AgentRequest("outreach", "Draft", {}), OutreachDraft)
    finally:
        container.store.connection.close()


def test_non_live_runner_is_reported_as_disabled():
    _, mode = agent_runner(Settings(runtime_mode="test"))
    assert mode == "disabled"
