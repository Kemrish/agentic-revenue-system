import pytest

from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Action, ActionType
from revenue_system.orchestration.delivery import OutboxDeliveryService


class FakeMail:
    async def send(self, recipient, subject, body, idempotency_key):
        self.args = (recipient, subject, body, idempotency_key)
        return "provider-1"


@pytest.mark.asyncio
async def test_delivery_sends_and_marks_outbox(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'delivery.db'}")
    store.add_outbox_once("mail-1", Action(ActionType.SEND_FIRST_TOUCH, "d1", {"recipient": "a@example.com", "subject": "Hi", "body": "Hello"}))
    mail = FakeMail()
    assert await OutboxDeliveryService(store, mail).deliver_pending() == ["mail-1"]
    assert store.pending_outbox() == []


@pytest.mark.asyncio
async def test_delivery_rejects_missing_recipient(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'delivery-missing.db'}")
    store.add_outbox_once("mail-1", Action(ActionType.SEND_FIRST_TOUCH, "d1", {"subject": "Hi", "body": "Hello"}))
    with pytest.raises(ValueError, match="missing recipient"):
        await OutboxDeliveryService(store, FakeMail()).deliver_pending()


@pytest.mark.asyncio
async def test_one_bad_item_does_not_hide_successful_delivery(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'batch.db'}")
    store.add_outbox_once("bad", Action(ActionType.SEND_FIRST_TOUCH, "d1", {"subject":"Hi", "body":"Draft"}))
    store.add_outbox_once("good", Action(ActionType.SEND_FOLLOW_UP, "d2", {"recipient":"a@example.com", "subject":"Hi", "body":"Draft"}))
    service = OutboxDeliveryService(store, FakeMail())
    assert await service.deliver_pending(continue_on_error=True) == ["good"]
    assert service.failures[0]["id"] == "bad"
    assert [r["id"] for r in store.pending_outbox()] == ["bad"]


@pytest.mark.asyncio
async def test_delivery_itself_enforces_kill_switch(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'stop.db'}")
    store.add_outbox_once("mail", Action(ActionType.SEND_FIRST_TOUCH, "d1", {"recipient":"a@example.com", "subject":"Hi", "body":"Draft"}))
    store.set_flag("global_kill_switch", True)
    mail = FakeMail()
    with pytest.raises(PermissionError, match="kill switch"):
        await OutboxDeliveryService(store, mail).deliver_pending()
    assert not hasattr(mail, "args")
    assert len(store.pending_outbox()) == 1


@pytest.mark.asyncio
async def test_contract_delivery_uses_esign_adapter(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'esign-delivery.db'}")
    store.add_outbox_once("contract", Action(ActionType.SEND_CONTRACT, "d1", {"document":"Agreement"}))

    class ESign:
        async def send_for_signature(self, document, key):
            assert document == "Agreement"
            return "signature-1"

    assert await OutboxDeliveryService(store, FakeMail(), esign=ESign()).deliver_pending() == ["contract"]
