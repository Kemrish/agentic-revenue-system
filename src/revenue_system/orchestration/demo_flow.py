import json
from pathlib import Path

from revenue_system.adapters.db import SQLiteStore
from revenue_system.agents.call_intelligence import CallIntelligenceAgent
from revenue_system.agents.deal_desk import DealDeskAgent, repair_from_supplied_data
from revenue_system.agents.execution import FakeRunner
from revenue_system.agents.outreach import OutreachAgent
from revenue_system.agents.reply_triage import ReplyTriageAgent
from revenue_system.domain.models import Action, ActionType
from revenue_system.orchestration.actions import route_action
from revenue_system.orchestration.events import DomainEvent
from revenue_system.orchestration.orchestrator import DealOrchestrator
from revenue_system.segments.registry import PackRegistry
from revenue_system.skills.io_validation import validate_io
from revenue_system.skills.templating import TemplateRenderer
from revenue_system.container import build_container
from revenue_system.settings import Settings

# Recorded agent responses used when no live model is configured.
DEMO_RESPONSES = {
    "reply_triage": {"label": "interested", "confidence": 0.96, "summary": "Requested a meeting"},
    "call_intelligence": {
        "qualification_fields": {"budget": "250000", "timeline": "90 days", "decision_maker": "VP Marketing"},
        "objections": [], "next_steps": ["prepare IO"],
        "lesson_candidate": "Measurement proof improves campaign conversations.",
    },
    "deal_desk": {"legal_entity": "Example Foods", "budget": 250000, "start_date": "2026-11-01",
                  "end_date": "2027-01-31", "line_items": [{"name": "Activate", "amount": 250000}]},
}
DEMO_LESSON = ("lesson-measurement", "global",
               "Lead with measurement proof: buyers ask how local campaign impact is proven.",
               ["fixtures/transcripts/brand-discovery.txt"])
DEMO_DEAL = "lead-brand-001"


async def run_demo(mode: str = "replay", root: Path = Path(".")) -> list[str]:
    """Run the deterministic vertical slice used by the demo and replay modes."""
    container = build_container(Settings()) if mode == "live" else None
    store = container.store if container else SQLiteStore("sqlite:///:memory:")
    output: list[str] = []
    if container:
        output.append(
            f"[runtime] provider={container.settings.llm_provider} "
            f"model={container.settings.openrouter_model if container.settings.llm_provider == 'openrouter' else 'claude'} "
            f"mail={container.settings.mail_mode} esign={container.settings.esign_mode} "
            f"side_effects={container.settings.live_side_effects_enabled}"
        )
    recipient = next((item.strip() for item in (container.settings.mail_allowed_recipients if container else "").split(",") if item.strip()), None)
    output += await run_pipeline(store, container.runner if container else FakeRunner(DEMO_RESPONSES), root, recipient)
    if container:
        approvals = container.store.connection.execute("SELECT COUNT(*) FROM approvals WHERE status='pending'").fetchone()[0]
        outbox = container.store.connection.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        auto = container.store.connection.execute("SELECT COUNT(*) FROM outbox WHERE action_type='send_follow_up'").fetchone()[0]
        denied = container.store.connection.execute("SELECT COUNT(*) FROM audit_log WHERE action='DENY'").fetchone()[0]
        output.append(f"[governance] auto={auto} pending_approvals={approvals} denied={denied} outbox_items={outbox}")
    return output


async def run_pipeline(store: SQLiteStore, runner, root: Path = Path("."), recipient: str | None = None) -> list[str]:
    """Drive every fixture lead, reply, and transcript through the governed lifecycle."""
    packs = PackRegistry(root / "packs")
    orchestrator = DealOrchestrator(store, root / "packs")
    leads = json.loads((root / "fixtures/leads.json").read_text(encoding="utf-8"))
    output: list[str] = []
    lesson_id, lesson_segment, statement, evidence = DEMO_LESSON
    if not store.connection.execute("SELECT 1 FROM lessons WHERE id=?", (lesson_id,)).fetchone():
        store.save_lesson(lesson_id, lesson_segment, statement, evidence, status="active")

    for lead in leads:
        event = DomainEvent("lead.created", f"fixture:lead:{lead['id']}", {
            **lead,
            "fit": 88 if lead["segment"] == "brand" else 82,
            "intent": 70,
            "engagement": 0,
        })
        store.add_event_once(event.event_id, event.event_type, event.payload)
        deal = orchestrator.handle(event)
        store.mark_event_processed(event.event_id)
        assert deal is not None and deal.score is not None
        output.append(f"[{deal.segment}] score={deal.score.total:.0f} tier={deal.score.tier.value}")

        pack = packs.get(deal.segment)
        lessons = [row["id"] for row in store.active_lessons(deal.segment)]
        draft = await OutreachAgent(runner).draft(deal, pack, lessons)
        store.audit("agent:outreach", "draft_proposed", f"subject={draft.subject!r} lessons_used={draft.lessons_used}", deal.id)
        case = lead.get("policy_case", "approval")
        action_type = ActionType.SEND_FOLLOW_UP if case == "auto" else ActionType.SEND_FIRST_TOUCH
        payload = {"subject": draft.subject, "body": draft.body, "lessons_used": draft.lessons_used,
                   **({"recipient": lead.get("email") or recipient} if lead.get("email") or recipient else {})}
        if case == "deny":
            payload["injection_detected"] = True
        decision = route_action(store, Action(action_type, deal.id, payload), deal, pack)
        if decision == "AUTO":
            orchestrator.advance(deal.id, "outreach", "outreach queued in outbox")
        output.append(f"[{deal.segment}] outreach={decision} lessons={draft.lessons_used}")

    triage = ReplyTriageAgent(runner)
    reply = await triage.classify((root / "fixtures/replies/interested.txt").read_text(encoding="utf-8"))
    store.audit("agent:reply_triage", "reply_classified", f"label={reply.label} confidence={reply.confidence:.2f}: {reply.summary}", DEMO_DEAL)
    if reply.label == "interested":
        orchestrator.advance(DEMO_DEAL, "engaged", "interested reply received", {"last_reply": reply.label})
    output.append(f"[reply] label={reply.label}")

    injection = await triage.classify((root / "fixtures/replies/prompt_injection.txt").read_text(encoding="utf-8"))
    store.audit("agent:reply_triage", "reply_flagged" if injection.injection_detected else "reply_classified",
                f"label={injection.label} injection_detected={injection.injection_detected}", "lead-deny-001")
    output.append(f"[safety] label={injection.label} flagged={injection.injection_detected}")

    brand = packs.get("brand")
    digest = await CallIntelligenceAgent(runner).digest((root / "fixtures/transcripts/brand-discovery.txt").read_text(encoding="utf-8"), brand.qualification_fields)
    orchestrator.advance(DEMO_DEAL, "meeting", "discovery call transcript received")
    store.audit("agent:call_intelligence", "call_digested", f"fields={digest.qualification_fields} next_steps={digest.next_steps}", DEMO_DEAL)
    missing = [name for name in brand.qualification_fields if not digest.qualification_fields.get(name)]
    if missing:
        store.audit("orchestrator", "exit_criteria_unmet", f"meeting -> qualified blocked; missing {missing}", DEMO_DEAL)
    else:
        orchestrator.advance(DEMO_DEAL, "qualified", "all pack qualification fields captured", digest.qualification_fields)
    if digest.lesson_candidate:
        store.save_lesson("lesson-call-brand-discovery", "brand", digest.lesson_candidate, ["fixtures/transcripts/brand-discovery.txt"])
    output.append(f"[call] fields={len(digest.qualification_fields)} lesson_created={bool(digest.lesson_candidate)}")

    io_inputs = digest.qualification_fields | {
        "legal_entity": "Example Foods",
        "budget": "250000",
        "start_date": "2026-11-01",
        "end_date": "2027-01-31",
        "line_items": [{"name": "Activate", "amount": 250000}],
    }
    io_draft = await DealDeskAgent(runner).draft(io_inputs, brand)
    io_draft = repair_from_supplied_data(io_draft, io_inputs)
    errors = validate_io(io_draft.as_io_data())
    rendered = TemplateRenderer(root / "packs").render("brand/templates/io.md.j2", {**io_draft.model_dump(), "line_items": io_draft.line_items})
    store.audit("agent:deal_desk", "io_drafted", f"valid={not errors} errors={errors or 'none'}", DEMO_DEAL)
    deal = store.get_deal(DEMO_DEAL)
    if not errors and deal is not None and deal.stage == "qualified":
        deal = orchestrator.advance(DEMO_DEAL, "proposal", "IO generated and validated")
        route_action(store, Action(ActionType.SEND_CONTRACT, DEMO_DEAL, {"document": rendered, **io_draft.model_dump()}), deal, brand)
    output.append(f"[io] valid={not errors} rendered={len(rendered) > 0} errors={', '.join(errors) if errors else 'none'}")
    return output
