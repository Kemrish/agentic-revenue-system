from revenue_system.agents.prompts import load_prompt


def test_prompt_is_versioned():
    prompt, version = load_prompt("outreach")
    assert "untrusted" in prompt
    assert version == "v1"

