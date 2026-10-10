import asyncio
import json
from pathlib import Path

from revenue_system.adapters.db import SQLiteStore
from revenue_system.agents.call_intelligence import CallIntelligenceAgent
from revenue_system.agents.deal_desk import DealDeskAgent
from revenue_system.agents.execution import FakeRunner
from revenue_system.agents.outreach import OutreachAgent
from revenue_system.agents.reply_triage import ReplyTriageAgent
from revenue_system.domain.models import Action, ActionType
from revenue_system.governance.approvals import ApprovalService
from revenue_system.orchestration.actions import route_action
from revenue_system.orchestration.events import DomainEvent
from revenue_system.orchestration.orchestrator import DealOrchestrator
from revenue_system.segments.registry import PackRegistry
from revenue_system.skills.io_validation import validate_io
from revenue_system.skills.templating import TemplateRenderer
from revenue_system.container import build_container
from revenue_system.settings import Settings


async def run_demo(mode: str = "replay", root: Path = Path(".")) -> list[str]:
    """Run the deterministic vertical slice used by the demo and replay modes."""
    container = build_container(Settings()) if mode == "live" else None
    store = container.store if container else SQLiteStore("sqlite:///:memory:")
    packs = PackRegistry(root / "packs")
    orchestrator = DealOrchestrator(store, root / "packs")
    leads = json.loads((root / "fixtures/leads.json").read_text(encoding="utf-8"))
    output: list[str] = []

    for lead in leads:
        event = DomainEvent("lead.created", f"fixture:lead:{lead['id']}", {
            **lead,
            "fit": 88 if lead["segment"] == "brand" else 82,
            "intent": 70,
            "engagement": 0,
        })
        deal = orchestrator.handle(event)
        assert deal is not None and deal.score is not None
        output.append(f"[{deal.segment}] score={deal.score.total:.0f} tier={deal.score.tier.value}")

        pack = packs.get(deal.segment)
        runner = container.runner if container else FakeRunner()
        draft = await OutreachAgent(runner).draft(deal, pack, ["lesson-measurement"])
        decision = route_action(store, Action(ActionType.SEND_FIRST_TOUCH, deal.id, {"subject": draft.subject, "body": draft.body}), deal, pack)
        output.append(f"[{deal.segment}] outreach={decision} lessons={draft.lessons_used}")

    triage_runner = container.runner if container else FakeRunner({"reply_triage": {"label": "interested", "confidence": 0.96, "summary": "Requested a meeting"}})
    reply = await ReplyTriageAgent(triage_runner).classify((root / "fixtures/replies/interested.txt").read_text(encoding="utf-8"))
    output.append(f"[reply] label={reply.label}")

    injection = await ReplyTriageAgent(triage_runner).classify((root / "fixtures/replies/prompt_injection.txt").read_text(encoding="utf-8"))
    output.append(f"[safety] label={injection.label} flagged={injection.injection_detected}")

    call_runner = container.runner if container else FakeRunner({"call_intelligence": {"qualification_fields": {"budget": "250000", "timeline": "90 days", "decision_maker": "VP Marketing"}, "objections": [], "next_steps": ["prepare IO"], "lesson_candidate": "Measurement proof improves campaign conversations."}, "deal_desk": {"legal_entity": "Example Foods", "budget": 250000, "start_date": "2026-11-01", "end_date": "2027-01-31", "line_items": [{"name": "Activate", "amount": 250000}]}})
    digest = await CallIntelligenceAgent(call_runner).digest((root / "fixtures/transcripts/brand-discovery.txt").read_text(encoding="utf-8"), packs.get("brand").qualification_fields)
    output.append(f"[call] fields={len(digest.qualification_fields)} lesson_created={bool(digest.lesson_candidate)}")

    io_inputs = digest.qualification_fields | {
        "legal_entity": "Example Foods",
        "budget": "250000",
        "start_date": "2026-11-01",
        "end_date": "2027-01-31",
        "line_items": [{"name": "Activate", "amount": 250000}],
    }
    io_draft = await DealDeskAgent(call_runner).draft(io_inputs, packs.get("brand"))
    errors = validate_io(io_draft.as_io_data())
    rendered = TemplateRenderer(root / "packs").render("brand/templates/io.md.j2", {**io_draft.model_dump(), "line_items": io_draft.line_items})
    output.append(f"[io] valid={not errors} rendered={len(rendered) > 0}")
    return output

