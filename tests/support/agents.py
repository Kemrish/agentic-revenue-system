"""Deterministic agent doubles for isolated workflow tests."""

from revenue_system.agents.base import AgentRequest


AGENT_RESPONSES = {
    "reply_triage": {"label":"interested", "confidence":.96, "summary":"Requested a meeting"},
    "call_intelligence": {
        "qualification_fields":{"budget":"250000", "timeline":"90 days", "decision_maker":"VP Marketing"},
        "objections":[], "next_steps":["prepare IO"], "lesson_candidate":"Measurement proof improves campaign conversations.",
    },
    "deal_desk": {"legal_entity":"Example Foods", "budget":250000, "start_date":"2026-11-01",
                  "end_date":"2027-01-31", "line_items":[{"name":"Activate", "amount":250000}]},
}


class FakeRunner:
    def __init__(self, responses=None):
        self.responses = responses or {}

    async def run(self, request: AgentRequest, output_type):
        response = self.responses.get(request.agent_name)
        if response is None and request.agent_name == "outreach":
            response = {"subject":f"Proposal for {request.context['company_name']}",
                        "body":f"Hello {request.context['contact_name']}", "confidence":.95,
                        "lessons_used":request.context.get("lessons_used", [])}
        if response is None:
            raise KeyError(f"No test response for {request.agent_name}")
        return output_type.model_validate(response)
