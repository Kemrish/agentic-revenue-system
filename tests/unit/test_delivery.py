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
