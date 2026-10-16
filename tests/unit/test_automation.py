import asyncio
import json
from pathlib import Path

import pytest

from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Action, ActionType, Deal
from revenue_system.governance.contract_review import ContractEdit, edit_contract
from revenue_system.governance.policy import PolicyEngine
from revenue_system.orchestration.delivery import OutboxDeliveryService
from revenue_system.orchestration.events import DomainEvent
from revenue_system.orchestration.orchestrator import DealOrchestrator
from revenue_system.orchestration.worker import EventWorker
from revenue_system.segments.schema import load_pack
from tests.support.agents import AGENT_RESPONSES, FakeRunner, approve_reviewed_contract

LEAD = {"lead_id":"a1", "segment":"brand", "company_name":"Account", "contact_name":"Amina",
        "email":"a@example.com", "fit":90, "intent":80}


@pytest.mark.parametrize("body", ["Our price is USD 500", "We guarantee results", "A 20% discount", "Sign the agreement", "Budget 1000"])
def test_unattended_messages_cannot_negotiate_sensitive_terms(body):
    result = PolicyEngine().evaluate(Action(ActionType.SEND_FIRST_TOUCH, "a1", {"recipient":"a@example.com", "subject":"Hello", "body":body}),
                                     Deal("a1", "brand", "Account", "Amina"), load_pack(Path("packs/brand/pack.yaml")))
    assert result.decision == "DENY"


def test_agent_pricing_change_is_denied_while_contract_review_is_required():
    deal, pack = Deal("a1", "brand", "Account", "Amina"), load_pack(Path("packs/brand/pack.yaml"))
    assert PolicyEngine().evaluate(Action(ActionType.CHANGE_PRICING, "a1"), deal, pack).decision == "DENY"
    assert PolicyEngine().evaluate(Action(ActionType.SEND_CONTRACT, "a1"), deal, pack).decision == "REQUIRE_APPROVAL"


@pytest.mark.asyncio
async def test_continuous_worker_needs_only_one_human_contract_checkpoint(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'automated.db'}")
    runner = FakeRunner(AGENT_RESPONSES)
    orchestrator, worker = DealOrchestrator(store, runner=runner), EventWorker(store)
    calls = []
    class Mail:
        async def send(self, *args):
            calls.append("mail")
            return "mail-reference"
    class ESign:
        async def send_for_signature(self, payload, key):
            assert payload["budget"] == 1500 and payload["human_approval"]["revision"] == 2
            calls.append("contract")
            return "signature-reference"
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run_forever(orchestrator, poll_seconds=.01, stop=stop,
                                                 delivery=OutboxDeliveryService(store, Mail(), esign=ESign())))
    async def stage(expected):
        async def poll():
            while not (store.get_deal("a1") and store.get_deal("a1").stage == expected):
                await asyncio.sleep(.01)
        await asyncio.wait_for(poll(), 5)
    try:
        worker.ingest(DomainEvent("lead.created", "lead", LEAD))
        await stage("outreach")
        assert not store.pending_approvals() and calls == ["mail"]
        worker.ingest(DomainEvent("reply.received", "reply", {"deal_id":"a1", "text":"Interested"}))
        worker.ingest(DomainEvent("transcript.ready", "call", {"deal_id":"a1", "transcript":"Discovery call"}))
        await stage("proposal")
        row = store.pending_approvals()[0]
        draft = json.loads(row["payload"])
        assert draft["review_status"] == "needs_terms" and draft["budget"] == 0 and not draft.get("artifact_sha256")
        assert calls == ["mail"]
        edit_contract(store, row["id"], ContractEdit(expected_revision=1, legal_entity="Human Entity", budget=1500,
            start_date="2026-11-01", end_date="2027-01-31", line_items=[{"name":"Service", "amount":1500}],
            signer_name="Amina", signer_email="a@example.com"), "human:operator")
        approve_reviewed_contract(store, row["id"])
        await stage("contracting")
        worker.ingest(DomainEvent("contract.signed", "signed", {"deal_id":"a1", "provider_id":"signature-reference"}))
        await stage("closed_won")
        assert calls == ["mail", "contract"]
        assert store.connection.execute("SELECT COUNT(*) FROM audit_log WHERE action='approval_approved'").fetchone()[0] == 1
    finally:
        stop.set()
        await asyncio.wait_for(task, 2)
        store.connection.close()


@pytest.mark.asyncio
async def test_followups_are_bounded_and_stop_on_reply(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'follow.db'}")
    orchestrator, worker = DealOrchestrator(store, runner=FakeRunner(AGENT_RESPONSES)), EventWorker(store)
    class Mail:
        async def send(self, *args):
            return "mail-reference"
    delivery = OutboxDeliveryService(store, Mail())
    worker.ingest(DomainEvent("lead.created", "lead", LEAD))
    await worker.run_once(orchestrator)
    await delivery.deliver_pending()
    await worker.run_once(orchestrator)
    for index in range(3):
        worker.ingest(DomainEvent("timer.due", f"timer-{index}", {"deal_id":"a1", "stage":"outreach", "sla_days":5}))
        await worker.run_once(orchestrator)
        await delivery.deliver_pending()
        await worker.run_once(orchestrator)
    assert store.connection.execute("SELECT COUNT(*) FROM outbox WHERE action_type='send_follow_up'").fetchone()[0] == 2
    assert not store.pending_approvals()
    # A queued follow-up also checks current reply/stage at delivery, not only draft time.
    store.add_outbox_once("stale-follow", Action(ActionType.SEND_FOLLOW_UP, "a1", {"recipient":"a@example.com", "subject":"Hello", "body":"Any thoughts?"}))
    worker.ingest(DomainEvent("reply.received", "reply", {"deal_id":"a1", "text":"Interested"}))
    await worker.run_once(orchestrator)
    assert await delivery.deliver_pending() == []
    assert store.connection.execute("SELECT status FROM outbox WHERE id='stale-follow'").fetchone()[0] == "cancelled"
    store.connection.close()


@pytest.mark.asyncio
async def test_legacy_pending_routine_review_is_released_but_rejection_is_preserved(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'migration.db'}")
    deal = Deal("a1", "brand", "Account", "Amina", stage="scored")
    store.save_deal(deal)
    payload = {"recipient":"a@example.com", "subject":"Hello", "body":"Can we discuss your needs?"}
    store.add_approval("old-pending", Action(ActionType.SEND_FIRST_TOUCH, "a1", payload))
    store.save_deal(Deal("rejected", "brand", "Other", "Contact"))
    store.add_approval("old-rejected", Action(ActionType.SEND_FIRST_TOUCH, "rejected", payload))
    from revenue_system.governance.approvals import ApprovalService
    ApprovalService(store).decide("old-rejected", False, "Not appropriate")
    worker, orchestrator = EventWorker(store), DealOrchestrator(store)
    await worker.run_once(orchestrator)
    await worker.run_once(orchestrator)
    assert store.get_approval("old-pending")["status"] == "auto_released"
    assert store.get_approval("old-rejected")["status"] == "rejected"
    assert len(store.pending_outbox()) == 1 and store.rejected_approvals_count() == 1
    store.connection.close()
