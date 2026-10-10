from datetime import date

from pydantic import BaseModel

from revenue_system.segments.schema import SegmentPack
from revenue_system.skills.io_validation import IOData

from .base import AgentRequest, AgentRunner


class IODraft(BaseModel):
    legal_entity: str
    budget: float
    start_date: str
    end_date: str
    line_items: list[dict[str, float | str]]

    def as_io_data(self) -> IOData:
        return IOData(self.legal_entity, self.budget, date.fromisoformat(self.start_date), date.fromisoformat(self.end_date), self.line_items)


class DealDeskAgent:
    def __init__(self, runner: AgentRunner) -> None:
        self.runner = runner

    async def draft(self, deal_fields: dict, pack: SegmentPack) -> IODraft:
        request = AgentRequest(
            agent_name="deal_desk",
            task="Map supplied deal data to structured IO fields. Do not invent prices, terms, or legal language.",
            context={"deal_fields": deal_fields, "segment": pack.segment},
        )
        return await self.runner.run(request, IODraft)

