from pathlib import Path

PROMPT_ROOT = Path(__file__).parent / "prompts"


def load_prompt(agent_name: str) -> tuple[str, str]:
    path = PROMPT_ROOT / f"{agent_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Missing prompt for agent: {agent_name}")
    return path.read_text(encoding="utf-8"), "v1"

