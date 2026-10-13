import asyncio
import json
from pathlib import Path

from revenue_system.adapters.db import SQLiteStore
from revenue_system.agents.call_intelligence import CallIntelligenceAgent
from revenue_system.agents.deal_desk import DealDeskAgent, repair_from_supplied_data
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
    if container:
        output.append(
            f"[runtime] provider={container.settings.llm_provider} "
            f"model={container.settings.openrouter_model if container.settings.llm_provider == 'openrouter' else 'claude'} "
            f"mail={container.settings.mail_mode} esign={container.settings.esign_mode} "
            f"side_effects={container.settings.live_side_effects_enabled}"
        )

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
        test_recipient = next((item.strip() for item in (container.settings.mail_allowed_recipients if container else "").split(",") if item.strip()), None)
        case = lead.get("policy_case", "approval")
        action_type = ActionType.SEND_FOLLOW_UP if case == "auto" else ActionType.SEND_FIRST_TOUCH
        payload = {"subject": draft.subject, "body": draft.body, **({"recipient": lead.get("email") or test_recipient} if lead.get("email") or test_recipient else {})}
        if case == "deny":
            payload["injection_detected"] = True
        decision = route_action(store, Action(action_type, deal.id, payload), deal, pack)
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
    io_draft = repair_from_supplied_data(io_draft, io_inputs)
    errors = validate_io(io_draft.as_io_data())
    rendered = TemplateRenderer(root / "packs").render("brand/templates/io.md.j2", {**io_draft.model_dump(), "line_items": io_draft.line_items})
    output.append(f"[io] valid={not errors} rendered={len(rendered) > 0} errors={', '.join(errors) if errors else 'none'}")
    if container:
        approvals = container.store.connection.execute("SELECT COUNT(*) FROM approvals WHERE status='pending'").fetchone()[0]
        outbox = container.store.connection.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        auto = container.store.connection.execute("SELECT COUNT(*) FROM outbox WHERE action_type='send_follow_up'").fetchone()[0]
        denied = container.store.connection.execute("SELECT COUNT(*) FROM audit_log WHERE action='DENY'").fetchone()[0]
        output.append(f"[governance] auto={auto} pending_approvals={approvals} denied={denied} outbox_items={outbox}")
    return output

