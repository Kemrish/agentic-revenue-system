import pytest

from revenue_system.agents.tools import tools_for


def test_reply_triage_has_no_tools():
    assert tools_for("reply_triage") == ()


def test_unknown_agent_scope_is_rejected():
    with pytest.raises(ValueError):
        tools_for("unknown")

