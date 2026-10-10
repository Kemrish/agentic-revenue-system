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
        try:
            start_date = date.fromisoformat(self.start_date)
            end_date = date.fromisoformat(self.end_date)
            date_error = None
        except ValueError:
            start_date = date.min
            end_date = date.min
            date_error = "start_date and end_date must use YYYY-MM-DD format"
        return IOData(self.legal_entity, self.budget, start_date, end_date, self.line_items, date_error)


class DealDeskAgent:
    def __init__(self, runner: AgentRunner) -> None:
        self.runner = runner

    async def draft(self, deal_fields: dict, pack: SegmentPack) -> IODraft:
        request = AgentRequest(
            agent_name="deal_desk",
            task="Map supplied deal data to structured IO fields. Return every field, including start_date and end_date as YYYY-MM-DD strings. If a required value is missing, return an empty string so deterministic validation can report it. Do not invent prices, terms, or legal language.",
            context={"deal_fields": deal_fields, "segment": pack.segment},
        )
        return await self.runner.run(request, IODraft)


def repair_from_supplied_data(draft: IODraft, supplied: dict) -> IODraft:
    """Reconcile the draft against trusted upstream deal data.

    Complete upstream commercial fields are canonical. This prevents a model
    from changing a budget or line-item total while preserving the agent's
    mapping role and keeping validation as the final authority.
    """
    updates: dict[str, object] = {}
    for field in ("legal_entity", "start_date", "end_date"):
        if not getattr(draft, field) and supplied.get(field):
            updates[field] = supplied[field]
    if supplied.get("budget") is not None:
        updates["budget"] = float(supplied["budget"])
    if supplied.get("line_items"):
        updates["line_items"] = supplied["line_items"]
    return draft.model_copy(update=updates)

