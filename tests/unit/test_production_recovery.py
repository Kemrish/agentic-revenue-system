"""Restart, concurrency, consent, and recovery regression coverage."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from revenue_system.adapters.db import LeaseLostError, SQLiteStore
from revenue_system.domain.models import Action, ActionType, Deal
from revenue_system.governance.approvals import ApprovalService
from revenue_system.governance.policy import PolicyEngine
from revenue_system.orchestration.delivery import OutboxDeliveryService
from revenue_system.orchestration.events import DomainEvent
from revenue_system.orchestration.orchestrator import DealOrchestrator
from revenue_system.orchestration.worker import EventWorker
from revenue_system.segments.registry import PackRegistry
from tests.support.agents import FakeRunner


@pytest.fixture
def stores(tmp_path):
    url = f"sqlite:///{tmp_path / 'durable.db'}"
    first, second = SQLiteStore(url), SQLiteStore(url)
    yield first, second
    first.connection.close()
    second.connection.close()


def test_claim_is_exclusive_and_recovers_after_process_restart(stores):
    first, second = stores
    first.add_event_once("event", "lead.created", {})
    assert first.claim("events", "event", "process-1", 300, 5)
    assert not second.claim("events", "event", "process-2", 300, 5)
    assert not second.pending_events()
    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    first.connection.execute("UPDATE events SET lease_until=? WHERE id='event'", (expired,))
    first.connection.commit()
    assert second.claim("events", "event", "process-2", 300, 5)
    row = second.connection.execute("SELECT claimed_by,attempts FROM events").fetchone()
    assert (row["claimed_by"], row["attempts"]) == ("process-2", 2)
    with pytest.raises(LeaseLostError):
        with first.transaction():
            first.audit("old-process", "must_rollback", "stale")
            first.assert_claim("events", "event", "process-1")
    assert not first.connection.execute("SELECT * FROM audit_log").fetchall()


@pytest.mark.asyncio
async def test_two_workers_do_not_process_the_same_event(stores):
    first, second = stores
    first.add_event_once("event", "lead.created", {})
    started, finish = asyncio.Event(), asyncio.Event()
    calls = []

    class Handler:
        async def process(self, event):
            calls.append(event.event_id)
            started.set()
            await finish.wait()

    task = asyncio.create_task(EventWorker(first).run_once(Handler()))
    await started.wait()
    result = await EventWorker(second).run_once(Handler())
    assert result["processed"] == 0
    finish.set()
    assert (await task)["processed"] == 1
    assert calls == ["event"]


@pytest.mark.asyncio
async def test_two_delivery_processes_send_once_and_persist_provider_evidence(stores):
    first, second = stores
    first.add_outbox_once("mail", Action(ActionType.SEND_FIRST_TOUCH, "d1",
                          {"recipient":"test@example.com", "subject":"Subject", "body":"Body"}))
    started, finish = asyncio.Event(), asyncio.Event()
    calls = []

    class Mail:
        async def send(self, recipient, subject, body, key):
            calls.append(key)
            started.set()
            await finish.wait()
            return "provider-verified"

    task = asyncio.create_task(OutboxDeliveryService(first, Mail()).deliver_pending())
    await started.wait()
    assert await OutboxDeliveryService(second, Mail()).deliver_pending() == []
    finish.set()
    assert await task == ["mail"]
    assert calls == ["mail"]
    row = first.connection.execute("SELECT status, provider_id FROM outbox").fetchone()
    assert (row["status"], row["provider_id"]) == ("sent", "provider-verified")
    assert first.connection.execute("SELECT event_type FROM events").fetchone()[0] == "action.delivered"


@pytest.mark.asyncio
async def test_backoff_then_dead_letter_and_explicit_recovery(stores):
    first, _ = stores
    worker = EventWorker(first, max_attempts=2, retry_base_seconds=30)
    worker.ingest(DomainEvent("unknown", "event", {}))
    handler = DealOrchestrator(first)
    assert (await worker.run_once(handler))["failed"] == 1
    assert (await worker.run_once(handler))["failed"] == 0
    first.connection.execute("UPDATE events SET next_attempt_at=NULL")
    first.connection.commit()
    assert (await worker.run_once(handler))["failed"] == 1
    assert first.health()["events_dead"] == 1
    assert first.retry_failed("events", "event", "human:test")
    assert not first.retry_failed("events", "event", "human:test")
    row = first.connection.execute("SELECT status,attempts,last_error FROM events").fetchone()
    assert (row["status"], row["attempts"], row["last_error"]) == ("pending", 0, None)


@pytest.mark.asyncio
async def test_cancelled_event_releases_lease_and_rolls_back(stores):
    first, _ = stores
    started = asyncio.Event()

    class Handler:
        async def process(self, event):
            first.audit("test", "should_roll_back", "temporary")
            started.set()
            await asyncio.Event().wait()

    worker = EventWorker(first)
    worker.ingest(DomainEvent("test", "event", {}))
    task = asyncio.create_task(worker.run_once(Handler()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not first.connection.execute("SELECT * FROM audit_log").fetchall()
    assert len(first.pending_events()) == 1


@pytest.mark.asyncio
async def test_inbound_lead_uses_active_lesson_content_and_routes_first_touch(stores):
    first, _ = stores
    first.save_lesson("active", "brand", "Explain measured lift", ["reviewed call"], "active")
    first.save_lesson("proposed", "brand", "Unreviewed advice", ["untrusted call"], "proposed")
    requests = []

    class Runner(FakeRunner):
        async def run(self, request, output_type):
            requests.append(request)
            return await super().run(request, output_type)

    worker = EventWorker(first)
    lead = {"lead_id":"real-1", "company_name":"Real Account", "contact_name":"Amina", "segment":"brand",
            "fit":90, "intent":80, "email":"review@example.com", "policy_case":"auto"}
    worker.ingest(DomainEvent("lead.created", "provider:1", lead))
    handler = DealOrchestrator(first, runner=Runner())
    assert (await worker.run_once(handler))["processed"] == 1
    approval = first.get_approval("approval:send_first_touch:real-1")
    assert approval is not None
    assert json.loads(approval["payload"])["recipient"] == "review@example.com"
    assert requests[0].context["lessons"][0]["statement"] == "Explain measured lift"
    assert requests[0].context["lessons_used"] == ["active"]
    handler.advance("real-1", "outreach", "sent")
    worker.ingest(DomainEvent("lead.created", "provider:2", lead))
    await worker.run_once(handler)
    assert first.get_deal("real-1").stage == "outreach"
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_unsubscribe_blocks_previously_queued_mail_and_future_approval(stores):
    first, _ = stores
    deal = Deal("d1", "brand", "Account", "Contact", flags=["do_not_contact"])
    first.save_deal(deal)
    action = Action(ActionType.SEND_FOLLOW_UP, "d1", {"recipient":"contact@example.com", "subject":"Hi", "body":"Body"})
    first.add_outbox_once("mail", action)
    first.add_approval("approval", action)
    assert PolicyEngine().evaluate(action, deal, PackRegistry(Path("packs")).get("brand")).decision == "DENY"
    with pytest.raises(ValueError, match="unsubscribed"):
        ApprovalService(first).decide("approval", True)
    service = OutboxDeliveryService(first, mail=None)
    assert await service.deliver_pending(continue_on_error=True) == []
    assert first.health()["outbox_failed"] == 1
    assert "unsubscribed" in service.failures[0]["reason"]


def test_approval_joins_outer_transaction(stores):
    first, _ = stores
    first.add_approval("approval", Action(ActionType.SEND_FIRST_TOUCH, "d1"))
    with pytest.raises(RuntimeError):
        with first.transaction():
            ApprovalService(first).decide("approval", True)
            raise RuntimeError("simulated crash before event commit")
    assert first.get_approval("approval")["status"] == "pending"
    assert not first.pending_outbox()
    assert not first.connection.execute("SELECT * FROM audit_log").fetchall()


@pytest.mark.asyncio
async def test_worker_resumes_after_interrupted_drafting(stores):
    first, _ = stores

    class FailingRunner(FakeRunner):
        async def run(self, request, output_type):
            raise RuntimeError("model temporarily unavailable")

    worker = EventWorker(first)
    worker.ingest(DomainEvent("lead.created", "lead-1", {"lead_id":"account-1", "segment":"brand",
                  "company_name":"Account", "contact_name":"Amina", "fit":90, "intent":80}))
    assert (await worker.run_once(DealOrchestrator(first, runner=FailingRunner())))["failed"] == 1
    assert first.connection.execute("SELECT status FROM events").fetchone()[0] == "pending"
    assert first.get_deal("account-1") is None
    assert (await worker.run_once(DealOrchestrator(first, runner=FakeRunner())))["processed"] == 1
    assert first.get_approval("approval:send_first_touch:account-1") is not None


def test_signed_event_requires_delivered_contract_evidence(stores):
    first, _ = stores
    deal = Deal("d1", "brand", "Account", "Amina", stage="contracting")
    first.save_deal(deal)
    handler = DealOrchestrator(first)
    signed = DomainEvent("contract.signed", "signed", {"deal_id":"d1", "provider_id":"provider-1"})
    with pytest.raises(ValueError, match="delivered contract"):
        handler.handle(signed)
    first.add_outbox_once("contract", Action(ActionType.SEND_CONTRACT, "d1", {"document":"Agreement"}))
    first.mark_outbox_sent("contract", "provider-2")
    with pytest.raises(ValueError, match="reference"):
        handler.handle(signed)
    first.mark_outbox_sent("contract", "provider-1")
    assert handler.handle(signed).stage == "closed_won"


def test_additive_migration_preserves_existing_deal_and_approval(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE approvals(id TEXT PRIMARY KEY,deal_id TEXT,action_type TEXT,payload TEXT,status TEXT,created_at TEXT);
        INSERT INTO approvals VALUES('legacy','d1','send_first_touch','{}','pending','2026-10-01');
        CREATE TABLE outbox(id TEXT PRIMARY KEY,action_type TEXT,deal_id TEXT,payload TEXT,status TEXT,created_at TEXT);
        INSERT INTO outbox VALUES('old-mail','send_first_touch','d1','{}','pending','2026-10-01');
    """)
    old.close()
    store = SQLiteStore(f"sqlite:///{path}")
    try:
        assert store.get_approval("legacy")["status"] == "pending"
        row = store.pending_outbox()[0]
        assert row["id"] == "old-mail" and row["attempts"] == 0
        assert row["provider_id"] is None
    finally:
        store.connection.close()
