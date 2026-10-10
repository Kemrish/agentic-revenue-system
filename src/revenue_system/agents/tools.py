"""Agent-scoped tools.

These tools are read-oriented by design. Side effects remain behind the
orchestrator, policy engine, and outbox.
"""

from typing import Any, Callable


def crm_read(deal: dict[str, Any]) -> dict[str, Any]:
    return deal


def lesson_search(lessons: list[dict[str, Any]], segment: str) -> list[dict[str, Any]]:
    return [lesson for lesson in lessons if lesson.get("segment") in {segment, "global"} and lesson.get("status") == "active"]


def transcript_read(transcript: str) -> str:
    return transcript


def pipeline_query(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return rows


TOOL_SCOPES: dict[str, tuple[Callable[..., Any], ...]] = {
    "research": (crm_read,),
    "outreach": (crm_read, lesson_search),
    "reply_triage": (),
    "call_intelligence": (crm_read, lesson_search, transcript_read),
    "deal_desk": (crm_read,),
    "pipeline_analyst": (pipeline_query,),
}


def tools_for(agent_name: str) -> tuple[Callable[..., Any], ...]:
    try:
        return TOOL_SCOPES[agent_name]
    except KeyError as exc:
        raise ValueError(f"No tool scope registered for {agent_name}") from exc

