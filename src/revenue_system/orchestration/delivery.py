"""Deliver approved outbox actions through injected real adapters."""

import asyncio
import json
from uuid import uuid4

from revenue_system.adapters.db import LeaseLostError, SQLiteStore
from revenue_system.adapters.errors import AmbiguousDeliveryError
from revenue_system.domain.models import ActionType
from revenue_system.skills.contracts import validate_contract


class OutboxDeliveryService:
    def __init__(self, store: SQLiteStore, mail, fallback_recipient: str | None = None, esign=None, max_attempts: int = 5,
                 lease_seconds: int = 300, retry_base_seconds: float = 0, crm=None, settings=None) -> None:
        self.store = store
        self.mail = mail
        self.fallback_recipient = fallback_recipient
        self.esign = esign
        self.crm = crm
        self.settings = settings
        self.max_attempts = max_attempts
        self.lease_seconds = lease_seconds
        self.retry_base_seconds = retry_base_seconds
        self.owner = f"delivery:{uuid4().hex}"
        self.failures: list[dict[str, str]] = []

    async def deliver_pending(self, continue_on_error: bool = False) -> list[str]:
        delivered: list[str] = []
        self.failures = []
        for row in self.store.pending_outbox():
            if self.store.flag_enabled("global_kill_switch"):
                # Paused, not failed: the item keeps its retry budget.
                self.store.audit("delivery", "KILL_SWITCH", "Delivery paused; item remains pending", row["deal_id"])
                self.failures.append({"id": row["id"], "reason": "Global kill switch is enabled"})
                if not continue_on_error:
                    raise PermissionError("Global kill switch is enabled")
                break
            if not self.store.claim("outbox", row["id"], self.owner, self.lease_seconds, self.max_attempts):
                continue
            row = self.store.connection.execute("SELECT * FROM outbox WHERE id=?", (row["id"],)).fetchone()
            try:
                action_type = ActionType(row["action_type"])
                payload = json.loads(row["payload"])
                if payload.get("unsafe") or payload.get("injection_detected"):
                    # Can never succeed; park it immediately instead of retrying.
                    self.store.record_outbox_failure(row["id"], "unsafe action", 1)
                    raise PermissionError("Unsafe actions cannot be delivered")
                deal = self.store.get_deal(row["deal_id"])
                if deal and "do_not_contact" in deal.flags and action_type != ActionType.SYNC_CRM:
                    self.store.record_outbox_failure(row["id"], "Contact unsubscribed", 1)
                    raise PermissionError("Contact unsubscribed; delivery is blocked")
                if action_type in {ActionType.SEND_FIRST_TOUCH, ActionType.SEND_FOLLOW_UP}:
                    recipient = payload.get("recipient") or self.fallback_recipient
                    if not recipient:
                        raise ValueError("approved mail action is missing recipient")
                    provider_id = await asyncio.wait_for(self.mail.send(recipient, payload["subject"], payload["body"], row["id"]), self.lease_seconds * .8)
                elif action_type == ActionType.SEND_CONTRACT:
                    if self.esign is None:
                        raise ValueError("e-signature adapter is not configured")
                    validate_contract(payload)
                    provider_id = await asyncio.wait_for(self.esign.send_for_signature(payload, row["id"]), self.lease_seconds * .8)
                elif action_type == ActionType.SYNC_CRM:
                    if not self.crm or not self.settings or not self.settings.crm_sync_enabled or not self.settings.live_side_effects_enabled:
                        raise PermissionError("CRM write-back is not explicitly enabled")
                    if not deal or str(deal.fields.get("hubspot_contact_id")) != payload.get("contact_id"):
                        raise ValueError("CRM contact does not match this deal")
                    properties = {self.settings.hubspot_stage_property: deal.stage}
                    if deal.score:
                        properties[self.settings.hubspot_score_property] = str(deal.score.total)
                    provider_id = await asyncio.wait_for(asyncio.to_thread(self.crm.update_properties, "contacts", payload["contact_id"], properties, "revenue-system"), self.lease_seconds * .8)
                else:
                    raise ValueError(f"no delivery adapter for action type: {action_type.value}")
                if not isinstance(provider_id, str) or not provider_id.strip():
                    raise ValueError("Provider did not return a delivery reference")
                with self.store.transaction():
                    self.store.assert_claim("outbox", row["id"], self.owner)
                    self.store.mark_outbox_sent(row["id"], str(provider_id))
                    self.store.audit("delivery", "outbox_sent", f"{row['id']} provider_id={provider_id}", row["deal_id"])
                    self.store.add_event_once(f"delivered:{row['id']}", "action.delivered",
                                              {"deal_id": row["deal_id"], "action_type": action_type.value, "provider_id": str(provider_id)})
                delivered.append(row["id"])
            except LeaseLostError:
                self.failures.append({"id": row["id"], "reason": "Delivery lease expired; inspect provider evidence before recovery"})
            except asyncio.CancelledError:
                # A provider may have accepted the call: retain the lease and
                # stable idempotency key for reconciliation after interruption.
                raise
            except Exception as exc:
                status = self.store.connection.execute("SELECT status FROM outbox WHERE id=?", (row["id"],)).fetchone()["status"]
                if isinstance(exc, AmbiguousDeliveryError):
                    status = self.store.record_outbox_failure(row["id"], str(exc), 1)
                elif status in {"pending", "delivering"}:
                    status = self.store.record_outbox_failure(row["id"], str(exc), self.max_attempts, self.retry_base_seconds)
                self.store.audit("delivery", "outbox_dead_letter" if status == "failed" else "outbox_failed", f"{row['id']}: {exc}", row["deal_id"])
                self.failures.append({"id": row["id"], "reason": str(exc)})
                if not continue_on_error:
                    raise
        return delivered
