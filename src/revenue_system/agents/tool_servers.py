from dataclasses import dataclass
from typing import Callable

from .tools import tools_for


@dataclass(frozen=True)
class ToolServerSpec:
    agent_name: str
    tools: tuple[Callable, ...]


def tool_server_spec(agent_name: str) -> ToolServerSpec:
    """Describe an agent's MCP scope without giving it the policy layer."""
    return ToolServerSpec(agent_name, tools_for(agent_name))

