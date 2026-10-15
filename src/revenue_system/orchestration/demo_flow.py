import json
from pathlib import Path

from revenue_system.adapters.db import SQLiteStore
from revenue_system.agents.execution import FakeRunner
from revenue_system.agents.outreach import OutreachAgent
from revenue_system.agents.replay_responses import DEMO_RESPONSES
from revenue_system.domain.models import Action, ActionType
from revenue_system.orchestration.actions import route_action
from revenue_system.orchestration.events import DomainEvent
from revenue_system.orchestration.orchestrator import DealOrchestrator
from revenue_system.segments.registry import PackRegistry
from revenue_system.orchestration.worker import EventWorker
from revenue_system.container import build_container
from revenue_system.settings import Settings

DEMO_LESSON = ("lesson-measurement", "global",
               "Lead with measurement proof: buyers ask how local campaign impact is proven.",
               ["fixtures/transcripts/brand-discovery.txt"])
DEMO_DEAL = "lead-brand-001"
DEMO_TERMS = {"legal_entity": "Example Foods", "budget": "250000", "start_date": "2026-11-01", "end_date": "2027-01-31",
              "line_items": [{"name": "Activate", "amount": 250000}]}


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
    """Drive every fixture lead, reply, and transcript through the governed lifecycle.

    Leads are scored on ingest so the demo can seed outreach scenarios; replies
    and transcripts are recorded as events and processed by the same worker
    that serves the webhooks.
    """
    packs = PackRegistry(root / "packs")
    orchestrator = DealOrchestrator(store, root / "packs", runner)
    worker = EventWorker(store)
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
        worker.ingest(event)
        if not store.claim("events", event.event_id, worker.owner, worker.lease_seconds, worker.max_attempts):
            output.append(f"[{lead['segment']}] {lead['id']} duplicate event ignored")
            continue
        try:
            # Prepare before writing; interrupted model calls leave a retryable event.
            deal = store.get_deal(lead["id"]) or orchestrator._build_lead(event)
            pack = packs.get(deal.segment)
            lesson_rows = [dict(row) for row in store.active_lessons(deal.segment)]
            lessons = [row["id"] for row in lesson_rows]
            draft = await OutreachAgent(runner).draft(deal, pack, lessons,
                [{"id": row["id"], "statement": row["statement"], "evidence": row["evidence"]} for row in lesson_rows])
            case = lead.get("policy_case", "approval")
            action_type = ActionType.SEND_FOLLOW_UP if case == "auto" else ActionType.SEND_FIRST_TOUCH
            payload = {"subject": draft.subject, "body": draft.body, "lessons_used": draft.lessons_used,
                       **({"recipient": lead.get("email") or recipient} if lead.get("email") or recipient else {})}
            if case == "deny":
                payload["injection_detected"] = True
            with store.transaction():
                store.assert_claim("events", event.event_id, worker.owner)
                store.save_deal(deal)
                store.audit("orchestrator", "lead_scored", deal.score.reason, deal.id)
                store.audit("agent:outreach", "draft_proposed", f"subject={draft.subject!r} lessons_used={draft.lessons_used}", deal.id)
                decision = route_action(store, Action(action_type, deal.id, payload), deal, pack)
                if decision == "AUTO":
                    orchestrator.try_advance(deal.id, "outreach", "demo outreach queued in outbox")
                worker.mark_processed(event.event_id)
            output.append(f"[{deal.segment}] score={deal.score.total:.0f} tier={deal.score.tier.value}")
            output.append(f"[{deal.segment}] outreach={decision} lessons={draft.lessons_used}")
        except Exception as exc:
            store.record_event_failure(event.event_id, str(exc), worker.max_attempts)
            raise

    fixture = lambda path: (root / "fixtures" / path).read_text(encoding="utf-8")
    worker.ingest(DomainEvent("reply.received", "fixture:reply:interested", {"deal_id": DEMO_DEAL, "text": fixture("replies/interested.txt")}))
    worker.ingest(DomainEvent("reply.received", "fixture:reply:injection", {"deal_id": "lead-deny-001", "text": fixture("replies/prompt_injection.txt")}))
    worker.ingest(DomainEvent("transcript.ready", "fixture:transcript:brand-discovery", {
        "deal_id": DEMO_DEAL, "transcript_id": "brand-discovery", "transcript": fixture("transcripts/brand-discovery.txt"), "deal_terms": DEMO_TERMS}))
    await worker.run_once(orchestrator, {"reply.received", "transcript.ready"})

    deal = store.get_deal(DEMO_DEAL)
    flagged = store.get_deal("lead-deny-001")
    output.append(f"[reply] label={deal.fields.get('last_reply')}")
    output.append(f"[safety] label={'suspicious' if 'suspicious_reply' in flagged.flags else 'clear'} flagged={'suspicious_reply' in flagged.flags}")
    captured = [name for name in packs.get("brand").qualification_fields if deal.fields.get(name)]
    lesson = store.connection.execute("SELECT 1 FROM lessons WHERE id='lesson-call-brand-discovery'").fetchone()
    output.append(f"[call] fields={len(captured)} lesson_created={bool(lesson)}")
    contract = store.get_approval(f"approval:send_contract:{DEMO_DEAL}")
    errors = store.connection.execute("SELECT detail FROM audit_log WHERE deal_id=? AND action='io_invalid' ORDER BY id DESC", (DEMO_DEAL,)).fetchone()
    output.append(f"[io] valid={contract is not None} rendered={bool(contract and json.loads(contract['payload']).get('document'))} errors={errors['detail'] if errors else 'none'}")
    return output
