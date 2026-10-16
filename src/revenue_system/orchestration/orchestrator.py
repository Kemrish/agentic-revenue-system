from datetime import datetime, timedelta, timezone
from pathlib import Path

from revenue_system.adapters.db import SQLiteStore
from revenue_system.agents.call_intelligence import CallIntelligenceAgent
from revenue_system.agents.deal_desk import IODraft, repair_from_supplied_data
from revenue_system.agents.outreach import OutreachAgent
from revenue_system.agents.reply_triage import ReplyTriageAgent
from revenue_system.domain.models import Action, ActionType, Deal
from revenue_system.domain.stages import can_transition, transition
from revenue_system.orchestration.actions import route_action
from revenue_system.orchestration.events import DomainEvent
from revenue_system.segments.paths import packs_path
from revenue_system.segments.registry import PackRegistry
from revenue_system.skills.contracts import bind_contract
from revenue_system.skills.io_validation import validate_io
from revenue_system.skills.scoring import calculate_score
from revenue_system.skills.templating import TemplateRenderer
from revenue_system.skills.tracking import check_stall

# Engagement evidence implied by each reply label (0-100, same scale as fit and intent).
ENGAGEMENT_BY_REPLY = {"interested": 80, "objection": 40, "not_now": 25, "unsubscribe": 0, "suspicious": 0}
REPLY_TARGET_STAGE = {"interested": "engaged", "objection": "engaged", "unsubscribe": "closed_lost"}
EVENT_TYPES = {"lead.created", "reply.received", "transcript.ready", "action.delivered", "contract.signed", "timer.due"}


class DealOrchestrator:
    """Owns deal state: every stage change, score, and routed action starts here.

    Handlers run agents first and write afterwards, so the database write lock
    is never held while waiting on a model.
    """

    def __init__(self, store: SQLiteStore, packs_root: Path | None = None, runner=None, providers=None, crm_sync_enabled: bool = False) -> None:
        self.store = store
        self.packs_root = packs_path(packs_root)
        self.packs = PackRegistry(self.packs_root)
        self.runner = runner
        self.providers = providers
        self.crm_sync_enabled = crm_sync_enabled

    def handle(self, event: DomainEvent) -> Deal | None:
        """Deterministic events that need no agent."""
        handlers = {
            "lead.created": self._create_and_score,
            "action.delivered": self._on_delivered,
            "contract.signed": self._on_signed,
            "timer.due": self._on_timer,
        }
        handler = handlers.get(event.event_type)
        return handler(event) if handler else None

    async def process(self, event: DomainEvent) -> Deal | None:
        """Entry point for the worker: every known event type, agent-backed or not."""
        if event.event_type.startswith("provider."):
            if self.providers is None:
                raise ValueError("Provider event resolution is not configured")
            event = await self.providers.resolve(event)
        if event.event_type not in EVENT_TYPES:
            raise ValueError(f"No handler for event type: {event.event_type}")
        if event.event_type == "lead.created" and self.runner is not None:
            deal = await self._on_lead(event)
        elif event.event_type == "reply.received":
            deal = await self._on_reply(event)
        elif event.event_type == "transcript.ready":
            deal = await self._on_transcript(event)
        elif event.event_type == "timer.due":
            deal = await self._on_follow_up_timer(event)
        else:
            deal = self.handle(event)
        if self.crm_sync_enabled and deal and deal.fields.get("hubspot_contact_id") and not (
                event.event_type == "action.delivered" and event.payload.get("action_type") == "sync_crm"):
            queued = self.store.add_outbox_once(f"crm-sync:{event.event_id}", Action(ActionType.SYNC_CRM, deal.id,
                                       {"contact_id": str(deal.fields["hubspot_contact_id"])}))
            if queued:
                self.store.audit("policy", "AUTO", "Configured bounded CRM score/stage synchronization queued", deal.id)
        return deal

    def advance(self, deal_id: str, target: str, reason: str, fields: dict | None = None) -> Deal:
        """Move a deal one guarded step, record why, and restart its stage SLA."""
        deal = self._deal(deal_id)
        source = deal.stage
        deal.stage = transition(source, target)
        deal.flags = [flag for flag in deal.flags if flag != "stalled"]
        deal.fields.update(fields or {})
        deal.updated_at = datetime.now(timezone.utc)
        self.store.save_deal(deal)
        self.store.audit("orchestrator", "stage_changed", f"{source} -> {target}: {reason}", deal.id)
        sla_days = self.packs.get(deal.segment).sla_days.get(target)
        if sla_days:
            self.store.schedule_timer(f"sla:{deal.id}", deal.id, "timer.due", deal.updated_at + timedelta(days=sla_days),
                                      {"deal_id": deal.id, "stage": target, "sla_days": sla_days})
        else:
            self.store.cancel_timer(f"sla:{deal.id}")
        return deal

    def try_advance(self, deal_id: str, target: str, reason: str, fields: dict | None = None) -> bool:
        """Advance when the state machine allows it; otherwise record why not."""
        deal = self._deal(deal_id)
        if deal.stage == target:
            if fields:
                deal.fields.update(fields)
                self.store.save_deal(deal)
            return True
        if not can_transition(deal.stage, target):
            self.store.audit("orchestrator", "transition_skipped", f"{deal.stage} -> {target} not allowed: {reason}", deal.id)
            return False
        self.advance(deal_id, target, reason, fields)
        return True

    def _deal(self, deal_id: str) -> Deal:
        deal = self.store.get_deal(deal_id)
        if deal is None:
            raise ValueError(f"Unknown deal: {deal_id}")
        return deal

    def _require_runner(self):
        if self.runner is None:
            raise RuntimeError("This event needs an agent runner; start the worker with one configured")
        return self.runner

    def _create_and_score(self, event: DomainEvent) -> Deal:
        deal_id = event.payload.get("deal_id") or event.payload.get("lead_id") or event.payload.get("id")
        existing = self.store.get_deal(deal_id)
        if existing is not None:
            return existing
        deal = self._build_lead(event)
        self.store.save_deal(deal)
        self.store.audit("orchestrator", "lead_scored", deal.score.reason, deal.id)
        return deal

    def _build_lead(self, event: DomainEvent) -> Deal:
        payload = event.payload
        deal = Deal(
            id=payload.get("deal_id") or payload.get("lead_id") or payload["id"],
            segment=payload["segment"],
            company_name=payload["company_name"],
            contact_name=payload["contact_name"],
            fields=payload,
        )
        deal.stage = transition(deal.stage, "enriched")
        deal.fields["enrichment_status"] = "complete"
        pack = self.packs.get(deal.segment)
        features = {
            "fit": float(payload.get("fit", 0)),
            "intent": float(payload.get("intent", 0)),
            "engagement": float(payload.get("engagement", 0)),
        }
        deal.score = calculate_score(features, pack)
        deal.stage = transition(deal.stage, "scored")
        deal.updated_at = datetime.now(timezone.utc)
        return deal

    async def _on_lead(self, event: DomainEvent) -> Deal:
        deal_id = event.payload.get("deal_id") or event.payload.get("lead_id") or event.payload.get("id")
        existing = self.store.get_deal(deal_id)
        if existing is not None:
            self.store.audit("orchestrator", "duplicate_lead_ignored", event.event_id, deal_id)
            return existing
        deal = self._build_lead(event)
        pack = self.packs.get(deal.segment)
        lessons = [dict(row) for row in self.store.active_lessons(deal.segment)]
        draft = await OutreachAgent(self._require_runner()).draft(
            deal, pack, [row["id"] for row in lessons],
            [{"id": row["id"], "statement": row["statement"], "evidence": row["evidence"]} for row in lessons])
        self.store.save_deal(deal)
        self.store.audit("orchestrator", "lead_scored", deal.score.reason, deal.id)
        self.store.audit("agent:outreach", "draft_proposed", f"subject={draft.subject!r} lessons_used={draft.lessons_used}", deal.id)
        route_action(self.store, Action(ActionType.SEND_FIRST_TOUCH, deal.id, {
            "subject": draft.subject, "body": draft.body, "recipient": deal.fields.get("email"),
            "lessons_used": draft.lessons_used,
        }), deal, pack)
        return deal

    async def _on_reply(self, event: DomainEvent) -> Deal:
        payload = event.payload
        deal = self._deal(payload["deal_id"])
        reply = await ReplyTriageAgent(self._require_runner()).classify(payload["text"])

        self.store.audit("agent:reply_triage", "reply_flagged" if reply.injection_detected else "reply_classified",
                         f"label={reply.label} confidence={reply.confidence:.2f} injection_detected={reply.injection_detected}: {reply.summary}", deal.id)
        if reply.injection_detected:
            # Untrusted instructions never move a deal; a human looks at the flag.
            if "suspicious_reply" not in deal.flags:
                deal.flags.append("suspicious_reply")
            self.store.save_deal(deal)
            return deal
        deal.fields["last_reply"] = reply.label
        if reply.label == "unsubscribe" and "do_not_contact" not in deal.flags:
            deal.flags.append("do_not_contact")
        if deal.score:
            engagement = ENGAGEMENT_BY_REPLY.get(reply.label, 0)
            deal.score = calculate_score({"fit": deal.score.fit, "intent": deal.score.intent, "engagement": engagement},
                                         self.packs.get(deal.segment))
            deal.fields["engagement"] = engagement
            self.store.audit("orchestrator", "lead_rescored", deal.score.reason, deal.id)
        self.store.save_deal(deal)
        target = REPLY_TARGET_STAGE.get(reply.label)
        if target:
            self.try_advance(deal.id, target, f"{reply.label} reply received", {"last_reply": reply.label})
        return self._deal(deal.id)

    async def _on_transcript(self, event: DomainEvent) -> Deal:
        payload = event.payload
        deal = self._deal(payload["deal_id"])
        pack = self.packs.get(deal.segment)
        runner = self._require_runner()
        transcript_id = payload.get("transcript_id") or event.event_id
        digest = await CallIntelligenceAgent(runner).digest(payload["transcript"], pack.qualification_fields)
        # Commercial qualification is confirmed by the human contract checkpoint,
        # not invented by call intelligence just to pass a stage gate.
        sensitive = {"budget", "price", "pricing", "legal_entity", "start_date", "end_date", "line_items"}
        missing = [name for name in pack.qualification_fields if name not in sensitive and not digest.qualification_fields.get(name)]
        terms = payload.get("deal_terms") or {}
        empty = IODraft(legal_entity="", budget=0, start_date="", end_date="", line_items=[])
        try:
            io_draft = repair_from_supplied_data(empty, terms)
        except (ValueError, TypeError):
            io_draft = empty

        self.try_advance(deal.id, "meeting", "call transcript received")
        self.store.audit("agent:call_intelligence", "call_digested",
                         f"fields={digest.qualification_fields} next_steps={digest.next_steps}", deal.id)
        if digest.lesson_candidate:
            self.store.save_lesson(f"lesson-call-{transcript_id}", deal.segment, digest.lesson_candidate, [f"transcript {transcript_id}"])
        if missing:
            self.store.audit("orchestrator", "exit_criteria_unmet", f"meeting -> qualified blocked; missing {missing}", deal.id)
            return self._deal(deal.id)
        if not self.try_advance(deal.id, "qualified", "all pack qualification fields captured", digest.qualification_fields):
            return self._deal(deal.id)
        errors = validate_io(io_draft.as_io_data())
        self.store.audit("system:deal_desk", "io_drafted", f"valid={not errors} errors={errors or 'none'}; human review required", deal.id)
        rendered = TemplateRenderer(self.packs_root).render(f"{pack.segment}/{pack.templates.contract}",
                                                             {**io_draft.model_dump(), "line_items": io_draft.line_items})
        deal = self.advance(deal.id, "proposal", "Contract draft ready for the human commercial checkpoint")
        if errors:
            rendered = "DRAFT — Human commercial input required\n\nAccount: " + deal.company_name + "\n\nNo price or legal commitment has been approved. Complete the sensitive terms in the contract editor."
        base = {"document": rendered, **io_draft.model_dump()}
        contract = (base | {"signer_email": deal.fields.get("email", ""), "signer_name": deal.contact_name}) if errors else bind_contract(base, deal.fields.get("email", ""), deal.contact_name)
        contract.update(revision=1, review_status="needs_terms" if errors else "ready", review_errors=errors,
                        additional_terms="", terms_source="supplied_data" if terms else "missing - human input required")
        route_action(self.store, Action(ActionType.SEND_CONTRACT, deal.id, contract), deal, pack)
        return deal

    async def _on_follow_up_timer(self, event: DomainEvent) -> Deal:
        deal = self._on_timer(event)
        pack = self.packs.get(deal.segment)
        if deal.stage != "outreach" or event.payload.get("stage") != "outreach" or deal.fields.get("last_reply"):
            return deal
        count = self.store.connection.execute("SELECT COUNT(*) FROM outbox WHERE deal_id=? AND action_type='send_follow_up'", (deal.id,)).fetchone()[0]
        pending = self.store.connection.execute("SELECT 1 FROM outbox WHERE deal_id=? AND action_type='send_follow_up' AND status IN ('pending','delivering')", (deal.id,)).fetchone()
        if count >= pack.follow_up_limit or pending or set(deal.flags) & {"do_not_contact", "suspicious_reply"}:
            return deal
        if self.store.flag_enabled("global_kill_switch"):
            self.store.schedule_timer(f"sla:{deal.id}", deal.id, "timer.due", datetime.now(timezone.utc) + timedelta(days=1), event.payload)
            return deal
        draft = await OutreachAgent(self._require_runner()).draft(deal, pack, follow_up=True)
        sequence = count + 1
        result = route_action(self.store, Action(ActionType.SEND_FOLLOW_UP, deal.id,
                              {"recipient": deal.fields.get("email"), "subject": draft.subject,
                               "body": draft.body, "follow_up_sequence": sequence}), deal, pack,
                              action_key=f"send_follow_up:{deal.id}:{sequence}")
        self.store.audit("agent:outreach", "follow_up_proposed", f"sequence={sequence} decision={result}", deal.id)
        return deal

    def _on_delivered(self, event: DomainEvent) -> Deal:
        payload = event.payload
        if payload["action_type"] == ActionType.SEND_CONTRACT.value:
            self.try_advance(payload["deal_id"], "contracting", "contract sent for signature")
        elif payload["action_type"] in {ActionType.SEND_FIRST_TOUCH.value, ActionType.SEND_FOLLOW_UP.value}:
            self.try_advance(payload["deal_id"], "outreach", "outreach delivered")
            deal = self._deal(payload["deal_id"])
            if payload["action_type"] == ActionType.SEND_FOLLOW_UP.value and deal.stage == "outreach" and not deal.fields.get("last_reply"):
                days = self.packs.get(deal.segment).sla_days.get("outreach", 7)
                self.store.schedule_timer(f"sla:{deal.id}", deal.id, "timer.due", datetime.now(timezone.utc) + timedelta(days=days),
                                          {"deal_id": deal.id, "stage": "outreach", "sla_days": days})
        return self._deal(payload["deal_id"])

    def _on_signed(self, event: DomainEvent) -> Deal:
        deal = self._deal(event.payload["deal_id"])
        if deal.stage == "closed_won":
            return deal
        signed_contract = self.store.connection.execute(
            "SELECT provider_id FROM outbox WHERE deal_id=? AND action_type='send_contract' AND status='sent'",
            (deal.id,)).fetchall()
        if not signed_contract or deal.stage != "contracting":
            raise ValueError("Signature event is waiting for a delivered contract in contracting stage")
        provider_id = event.payload.get("provider_id")
        if not provider_id or provider_id not in {row["provider_id"] for row in signed_contract}:
            raise ValueError("Signature provider reference does not match this deal")
        self.try_advance(event.payload["deal_id"], "closed_won", "contract signed")
        return self._deal(event.payload["deal_id"])

    def _on_timer(self, event: DomainEvent) -> Deal:
        payload = event.payload
        deal = self._deal(payload["deal_id"])
        if deal.stage != payload["stage"]:
            return deal  # The deal moved on; this SLA no longer applies.
        result = check_stall(deal.stage, deal.updated_at, int(payload["sla_days"]))
        if result.stalled and "stalled" not in deal.flags:
            deal.flags.append("stalled")
            self.store.save_deal(deal)
            self.store.audit("orchestrator", "deal_stalled", result.reason, deal.id)
        return deal

    def release_routine_reviews(self) -> None:
        """Migrate pending routine gates under current policy, never human rejections."""
        import json

        from revenue_system.governance.policy import PolicyEngine
        if self.store.flag_enabled("global_kill_switch"):
            return
        for row in self.store.pending_approvals():
            if row["action_type"] not in {"send_first_touch", "send_follow_up"}:
                continue
            deal = self.store.get_deal(row["deal_id"])
            if not deal:
                continue
            action = Action(ActionType(row["action_type"]), deal.id, json.loads(row["payload"]))
            decision = PolicyEngine().evaluate(action, deal, self.packs.get(deal.segment))
            if decision.decision == "DENY":
                with self.store.transaction():
                    updated = self.store.connection.execute("UPDATE approvals SET status='denied' WHERE id=? AND status='pending' AND payload=?", (row["id"], row["payload"]))
                    if updated.rowcount:
                        self.store.audit("policy", "DENY", f"Legacy routine gate {row['id']}: {decision.reason}", deal.id)
                continue
            if decision.decision != "AUTO":
                continue
            with self.store.transaction():
                updated = self.store.connection.execute("UPDATE approvals SET status='auto_released' WHERE id=? AND status='pending' AND payload=?", (row["id"], row["payload"]))
                if updated.rowcount != 1:
                    continue
                existing = self.store.connection.execute("SELECT 1 FROM outbox WHERE deal_id=? AND action_type=?", (deal.id, row["action_type"])).fetchone()
                if not existing:
                    self.store.add_outbox_once(f"{row['action_type']}:{deal.id}", action)
                self.store.audit("policy", "AUTO", f"Removed legacy routine approval gate {row['id']}; no human approval fabricated", deal.id)
