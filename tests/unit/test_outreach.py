import pytest
from pathlib import Path

from revenue_system.agents.base import AgentRequest, OutreachDraft
from tests.support.agents import FakeRunner
from revenue_system.agents.outreach import OutreachAgent
from revenue_system.domain.models import Deal
from revenue_system.segments.schema import load_pack


@pytest.mark.asyncio
async def test_outreach_agent_returns_typed_draft():
    pack = load_pack(Path("packs/brand/pack.yaml"))
    draft = await OutreachAgent(FakeRunner()).draft(Deal("d1", "brand", "Example", "Amina"), pack, ["lesson-1"])
    assert isinstance(draft, OutreachDraft)
    assert draft.lessons_used == ["lesson-1"]

