from pydantic import BaseModel, Field

from revenue_system.governance.guardrails import wrap_untrusted_content

from .base import AgentRequest, AgentRunner


class CallDigest(BaseModel):
    qualification_fields: dict[str, str] = Field(default_factory=dict)
    objections: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    lesson_candidate: str | None = None


class CallIntelligenceAgent:
    def __init__(self, runner: AgentRunner) -> None:
        self.runner = runner

    async def digest(self, transcript: str, qualification_fields: list[str]) -> CallDigest:
        request = AgentRequest(
            agent_name="call_intelligence",
            task="Extract only supported qualification fields, objections, next steps, and a concise lesson candidate from this transcript.",
            context={"transcript": wrap_untrusted_content(transcript, "call_transcript"), "qualification_fields": qualification_fields},
        )
        return await self.runner.run(request, CallDigest)

