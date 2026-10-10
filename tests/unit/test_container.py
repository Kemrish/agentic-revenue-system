from revenue_system.container import build_container
from revenue_system.settings import Settings
from revenue_system.adapters.fixtures.mail import FixtureMailAdapter


def test_replay_container_uses_fixture_side_effects():
    container = build_container(Settings(runtime_mode="replay"))
    assert isinstance(container.mail, FixtureMailAdapter)
    assert container.crm is None

