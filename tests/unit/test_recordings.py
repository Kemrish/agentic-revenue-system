import pytest

from revenue_system.agents.base import AgentRequest, OutreachDraft
from revenue_system.agents.execution import RecordedReplayRunner
from revenue_system.agents.recording import Recording, RecordingStore


@pytest.mark.asyncio
async def test_replay_rejects_changed_input(tmp_path):
    store = RecordingStore(tmp_path)
    request = AgentRequest("outreach", "draft", {"company": "Example"}, "v1")
    store.save(Recording("outreach", "v1", "wrong-hash", {"subject": "x", "body": "y"}))
    with pytest.raises(KeyError):
        await RecordedReplayRunner(store).run(request, OutreachDraft)


@pytest.mark.asyncio
async def test_replay_validates_output(tmp_path):
    from revenue_system.agents.recording import request_hash
    store = RecordingStore(tmp_path)
    request = AgentRequest("outreach", "draft", {"company": "Example"}, "v1")
    store.save(Recording("outreach", "v1", request_hash(request), {"subject": "x", "body": "y"}))
    result = await RecordedReplayRunner(store).run(request, OutreachDraft)
    assert result.subject == "x"

