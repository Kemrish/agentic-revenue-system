from revenue_system.domain.models import Deal
from revenue_system.segments.schema import SegmentPack

from .base import AgentRequest, AgentRunner, OutreachDraft


class OutreachAgent:
    def __init__(self, runner: AgentRunner) -> None:
        self.runner = runner

    async def draft(self, deal: Deal, pack: SegmentPack, lessons: list[str] | None = None,
                    lesson_context: list[dict] | None = None, follow_up: bool = False) -> OutreachDraft:
        lessons = lessons or []
        products = ", ".join(pack.messaging.get("products", []))
        request = AgentRequest(
            agent_name="outreach",
            task=("Draft a concise follow-up to unanswered outreach." if follow_up else "Draft a concise first-touch message.") +
                 " Use only supplied evidence. Never quote or mention pricing, budgets, discounts, contracts, payment terms, percentages or guarantees. Sensitive commercial decisions belong exclusively to the human contract review. Ask a simple discovery question; do not invent commitments.",
            context={
                "company_name": deal.company_name,
                "contact_name": deal.contact_name,
                "segment": deal.segment,
                "value_proposition": f"Cool AI can help with {products}.",
                "lessons_used": lessons,
                "lessons": lesson_context or [],
                "message_kind": "follow_up" if follow_up else "first_touch",
            },
        )
        return await self.runner.run(request, OutreachDraft)

