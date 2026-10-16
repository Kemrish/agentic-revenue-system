"""All four native webhook boundaries through the real durable lifecycle, offline."""

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from revenue_system import provider_webhooks, webhooks
from revenue_system.governance.contract_review import ContractEdit, edit_contract
from revenue_system.orchestration.delivery import OutboxDeliveryService
from revenue_system.orchestration.orchestrator import DealOrchestrator
from revenue_system.orchestration.provider_events import ProviderEventResolver
from revenue_system.orchestration.worker import EventWorker
from revenue_system.skills.contracts import validate_contract
from tests.support.agents import approve_reviewed_contract
from tests.support.local_sandbox import (
    SECRET,
    emit,
    sandbox_container,
    sandbox_settings,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("contact_id", ["101", "102"])
async def test_native_intake_to_confirmed_signature_without_external_services(tmp_path, monkeypatch, contact_id):
    settings = sandbox_settings(tmp_path / "acceptance.db")
    monkeypatch.setattr(provider_webhooks, "Settings", lambda: settings)
    container = sandbox_container(settings)
    store = container.store
    orchestrator = DealOrchestrator(store, runner=container.runner, providers=ProviderEventResolver(container))
    worker = EventWorker(store)
    delivery = OutboxDeliveryService(store, container.mail, esign=container.esign)
    deal_id = "hubspot-contact-" + contact_id
    with TestClient(webhooks.app) as client:
        assert emit(client, "leads").json()["accepted"] == 2
        assert (await worker.run_once(orchestrator))["processed"] == 2
        assert store.get_deal(deal_id).stage == "scored"
        assert not store.pending_approvals()
        await delivery.deliver_pending()
        await worker.run_once(orchestrator)
        assert emit(client, "reply", deal_id).status_code == 200
        await worker.run_once(orchestrator)
        assert store.get_deal(deal_id).stage == "engaged"
        deal = store.get_deal(deal_id)
        assert emit(client, "call", deal_id).status_code == 200
        await worker.run_once(orchestrator)
        assert store.get_deal(deal_id).stage == "proposal"
        approval = store.get_approval(f"approval:send_contract:{deal_id}")
        assert json.loads(approval["payload"])["review_status"] == "needs_terms"
        reviewed = edit_contract(store, approval["id"], ContractEdit(expected_revision=1, legal_entity=deal.company_name,
            budget=1000, start_date="2026-11-01", end_date="2027-01-31", line_items=[{"name":"Service", "amount":1000}],
            signer_name=deal.contact_name, signer_email="contact@sandbox.invalid"), "human:test")
        assert validate_contract(reviewed)
        approve_reviewed_contract(store, approval["id"])
        await delivery.deliver_pending()
        await worker.run_once(orchestrator)
        assert store.get_deal(deal_id).stage == "contracting"
        provider_id = store.connection.execute("SELECT provider_id FROM outbox WHERE deal_id=? AND action_type='send_contract'", (deal_id,)).fetchone()[0]
        stamp, kind = str(int(time.time())), "signature_request_all_signed"
        event = {"event_time": stamp, "event_type": kind, "event_hash": hmac.new(SECRET.encode(), (stamp+kind).encode(), hashlib.sha256).hexdigest()}
        response = client.post("/providers/dropbox-sign", files={"json": (None, json.dumps({"event": event, "signature_request": {"signature_request_id": provider_id}}))})
        assert response.status_code == 200
        await worker.run_once(orchestrator)
        assert store.get_deal(deal_id).stage == "closed_won"
        print(f"{deal.segment}: signed callbacks -> automatic outreach -> reply -> transcript -> one human contract edit/approval -> automatic signature delivery -> closed_won")
    store.connection.close()
