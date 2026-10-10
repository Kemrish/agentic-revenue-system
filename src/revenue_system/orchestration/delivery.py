"""Deliver approved outbox actions through injected real adapters."""

from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import ActionType


class OutboxDeliveryService:
    def __init__(self, store: SQLiteStore, mail) -> None:
        self.store = store
        self.mail = mail

    async def deliver_pending(self) -> list[str]:
        delivered: list[str] = []
        for row in self.store.pending_outbox():
            action_type = ActionType(row["action_type"])
            payload = __import__("json").loads(row["payload"])
            try:
                if action_type in {ActionType.SEND_FIRST_TOUCH, ActionType.SEND_FOLLOW_UP}:
                    recipient = payload.get("recipient")
                    if not recipient:
                        raise ValueError("approved mail action is missing recipient")
                    provider_id = await self.mail.send(recipient, payload["subject"], payload["body"], row["id"])
                else:
                    raise ValueError(f"no delivery adapter for action type: {action_type.value}")
                self.store.mark_outbox_sent(row["id"])
                self.store.audit("delivery", "outbox_sent", f"{row['id']} provider_id={provider_id}", row["deal_id"])
                delivered.append(row["id"])
            except Exception as exc:
                self.store.audit("delivery", "outbox_failed", f"{row['id']}: {exc}", row["deal_id"])
                raise
        return delivered
