from revenue_system.domain.models import Deal
from revenue_system.segments.schema import SegmentPack

from .base import AgentRequest, AgentRunner, OutreachDraft


class OutreachAgent:
    def __init__(self, runner: AgentRunner) -> None:
        self.runner = runner

    async def draft(self, deal: Deal, pack: SegmentPack, lessons: list[str] | None = None) -> OutreachDraft:
        lessons = lessons or []
        products = ", ".join(pack.messaging.get("products", []))
        request = AgentRequest(
            agent_name="outreach",
            task="Draft a concise first-touch message using only the supplied deal evidence and segment pack.",
            context={
                "company_name": deal.company_name,
                "contact_name": deal.contact_name,
                "segment": deal.segment,
                "value_proposition": f"Cool AI can help with {products}.",
                "lessons_used": lessons,
            },
        )
        return await self.runner.run(request, OutreachDraft)

