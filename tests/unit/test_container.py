from revenue_system.container import build_container
from revenue_system.settings import Settings
from revenue_system.adapters.fixtures.mail import FixtureMailAdapter


def test_replay_container_uses_fixture_side_effects():
    container = build_container(Settings(runtime_mode="replay"))
    assert isinstance(container.mail, FixtureMailAdapter)
    assert container.crm is None


def test_replay_runner_supports_all_demo_agents_without_provider_calls(tmp_path):
    import asyncio
    from revenue_system.agents.base import AgentRequest
    from revenue_system.agents.reply_triage import ReplyClassification

    container = build_container(Settings(_env_file=None, runtime_mode="replay", database_url=f"sqlite:///{tmp_path / 'container.db'}"))
    try:
        result = asyncio.run(container.runner.run(AgentRequest("reply_triage","Classify",{}), ReplyClassification))
        assert result.label == "interested"
    finally:
        container.store.connection.close()

