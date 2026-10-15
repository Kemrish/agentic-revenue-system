from types import SimpleNamespace

import pytest

from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Action, ActionType
from revenue_system.orchestration.delivery import OutboxDeliveryService
from revenue_system.orchestration.events import DomainEvent
from revenue_system.orchestration.orchestrator import DealOrchestrator
from revenue_system.orchestration.provider_events import ProviderEventResolver
from revenue_system.orchestration.worker import EventWorker
from revenue_system.settings import Settings
from tests.support.agents import AGENT_RESPONSES, FakeRunner


@pytest.mark.asyncio
async def test_provider_contact_retries_then_flows_through_scoring_approval_and_crm(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'native.db'}")
    class CRM:
        fail = True
        calls = []
        async def get_contact(self, key, fields):
            if self.fail:
                raise RuntimeError("Provider unavailable")
            return {"company": "Account", "firstname": "Amina", "email": "a@example.com", "ars_segment": "brand", "ars_fit": "90", "ars_intent": "80"}
        def update_properties(self, object_type, key, properties, source):
            self.calls.append((key, properties))
            return key
    crm = CRM()
    settings = Settings(crm_sync_enabled=True, live_side_effects_enabled=True)
    container = SimpleNamespace(store=store, settings=settings, crm=crm)
    orchestrator = DealOrchestrator(store, runner=FakeRunner(AGENT_RESPONSES), providers=ProviderEventResolver(container), crm_sync_enabled=True)
    worker = EventWorker(store)
    worker.ingest(DomainEvent("provider.hubspot.contact", "native-1", {"contact_id": "42"}))
    assert (await worker.run_once(orchestrator))["failed"] == 1
    assert not store.get_deal("hubspot-contact-42")
    crm.fail = False
    assert (await worker.run_once(orchestrator))["processed"] == 1
    assert store.pending_approvals()[0]["action_type"] == "send_first_touch"
    delivery = OutboxDeliveryService(store, None, crm=crm, settings=settings)
    assert await delivery.deliver_pending() == ["crm-sync:native-1"]
    assert crm.calls[0][0] == "42" and crm.calls[0][1]["ars_stage"] == "scored"
    await worker.run_once(orchestrator)
    assert store.pending_outbox() == []  # CRM delivery acknowledgement never loops.
    store.connection.close()


@pytest.mark.asyncio
async def test_ambiguous_provider_acceptance_is_parked_not_automatically_retried(tmp_path):
    from revenue_system.adapters.errors import AmbiguousDeliveryError
    store = SQLiteStore(f"sqlite:///{tmp_path / 'ambiguous.db'}")
    store.add_outbox_once("mail", Action(ActionType.SEND_FIRST_TOUCH, "d1", {"recipient": "a@example.com", "subject": "Subject", "body": "Body"}))
    class Mail:
        calls = 0
        async def send(self, *args):
            self.calls += 1
            raise AmbiguousDeliveryError("Inspect provider logs")
    mail = Mail()
    delivery = OutboxDeliveryService(store, mail)
    await delivery.deliver_pending(continue_on_error=True)
    await delivery.deliver_pending(continue_on_error=True)
    assert mail.calls == 1
    assert store.connection.execute("SELECT status FROM outbox WHERE id='mail'").fetchone()[0] == "failed"
    store.connection.close()


@pytest.mark.asyncio
async def test_contract_without_reviewed_artifact_never_reaches_provider(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'legacy.db'}")
    store.add_outbox_once("legacy", Action(ActionType.SEND_CONTRACT, "d1", {"document": "Old text"}))
    class ESign:
        called = False
        async def send_for_signature(self, *args):
            self.called = True
    esign = ESign()
    await OutboxDeliveryService(store, None, esign=esign).deliver_pending(continue_on_error=True)
    assert not esign.called and len(store.pending_outbox()) == 1
    store.connection.close()
