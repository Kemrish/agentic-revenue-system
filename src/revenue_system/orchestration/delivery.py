"""Deliver approved outbox actions through injected real adapters."""

from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import ActionType


class OutboxDeliveryService:
    def __init__(self, store: SQLiteStore, mail, fallback_recipient: str | None = None, esign=None) -> None:
        self.store = store
        self.mail = mail
        self.fallback_recipient = fallback_recipient
        self.esign = esign
        self.failures: list[dict[str, str]] = []

    async def deliver_pending(self, continue_on_error: bool = False) -> list[str]:
        delivered: list[str] = []
        self.failures = []
        for row in self.store.pending_outbox():
            action_type = ActionType(row["action_type"])
            payload = __import__("json").loads(row["payload"])
            try:
                if self.store.flag_enabled("global_kill_switch"):
                    self.store.audit("delivery", "KILL_SWITCH", "Delivery paused; item remains pending", row["deal_id"])
                    raise PermissionError("Global kill switch is enabled")
                if payload.get("unsafe") or payload.get("injection_detected"):
                    raise PermissionError("Unsafe actions cannot be delivered")
                if action_type in {ActionType.SEND_FIRST_TOUCH, ActionType.SEND_FOLLOW_UP}:
                    recipient = payload.get("recipient") or self.fallback_recipient
                    if not recipient:
                        raise ValueError("approved mail action is missing recipient")
                    provider_id = await self.mail.send(recipient, payload["subject"], payload["body"], row["id"])
                elif action_type == ActionType.SEND_CONTRACT:
                    if self.esign is None:
                        raise ValueError("e-signature adapter is not configured")
                    provider_id = await self.esign.send_for_signature(payload.get("document", ""), row["id"])
                else:
                    raise ValueError(f"no delivery adapter for action type: {action_type.value}")
                self.store.mark_outbox_sent(row["id"])
                self.store.audit("delivery", "outbox_sent", f"{row['id']} provider_id={provider_id}", row["deal_id"])
                delivered.append(row["id"])
            except Exception as exc:
                self.store.audit("delivery", "outbox_failed", f"{row['id']}: {exc}", row["deal_id"])
                self.failures.append({"id": row["id"], "reason": str(exc)})
                if not continue_on_error:
                    raise
                if self.store.flag_enabled("global_kill_switch"):
                    break
        return delivered
