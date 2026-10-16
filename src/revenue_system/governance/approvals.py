import json

from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Action
from revenue_system.orchestration.events import DomainEvent
from revenue_system.skills.contracts import validate_contract


class ApprovalService:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def request(self, approval_id: str, action: Action) -> None:
        self.store.add_approval(approval_id, action)
        self.store.audit("system", "approval_requested", action.action_type.value, action.deal_id)

    def decide(self, approval_id: str, approved: bool, rejection_reason: str | None = None, actor: str = "human",
               expected_revision: int | None = None, artifact_sha256: str | None = None) -> DomainEvent:
        rejection_reason = (rejection_reason or "").strip()
        if not approved and not rejection_reason:
            raise ValueError("A rejection reason is required")
        status = "approved" if approved else "rejected"
        # Decision, evidence, and queued action/lesson commit together. A second
        # operator cannot reverse a decision or queue the same action twice.
        with self.store.transaction():
            row = self.store.get_approval(approval_id)
            if row is None:
                raise ValueError("Approval not found")
            if approved:
                payload = json.loads(row["payload"])
                if row["action_type"] == "send_contract":
                    validate_contract(payload)
                    if expected_revision != payload.get("revision", 1) or artifact_sha256 != payload.get("artifact_sha256"):
                        raise ValueError("Approve the current reviewed revision and fingerprint; contract changed or review evidence is missing")
                deal = self.store.get_deal(row["deal_id"])
                if payload.get("unsafe") or payload.get("injection_detected") or (deal and set(deal.flags) & {"do_not_contact", "suspicious_reply"}):
                    raise ValueError("Unsafe or unsubscribed contact actions cannot be approved")
            updated = self.store.connection.execute(
                "UPDATE approvals SET status=?, rejection_reason=? WHERE id=? AND status='pending' AND payload=?",
                (status, rejection_reason if not approved else None, approval_id, row["payload"]),
            )
            if updated.rowcount != 1:
                raise ValueError("Approval has already been decided")
            detail = approval_id if approved else f"{approval_id}: {rejection_reason}"
            self.store.connection.execute(
                "INSERT INTO audit_log(deal_id,actor,action,detail,created_at) VALUES(?,?,?,?,datetime('now'))",
                (row["deal_id"], actor, f"approval_{status}", detail),
            )
            if approved:
                queued_payload = json.loads(row["payload"])
                if row["action_type"] == "send_contract":
                    queued_payload["human_approval"] = {"approval_id": approval_id,
                        "revision": expected_revision, "artifact_sha256": artifact_sha256, "actor": actor}
                self.store.connection.execute(
                    "INSERT OR IGNORE INTO outbox(id,action_type,deal_id,payload,status,created_at) VALUES(?,?,?,?,'pending',datetime('now'))",
                    (f"approved:{approval_id}", row["action_type"], row["deal_id"], json.dumps(queued_payload)),
                )
            else:
                deal = self.store.get_deal(row["deal_id"])
                self.store.connection.execute(
                    "INSERT OR IGNORE INTO lessons VALUES(?,?,?,?, 'proposed', datetime('now'))",
                    (f"rejection:{approval_id}", deal.segment if deal else "global",
                     f"Do not repeat {row['action_type']} for {deal.company_name if deal else row['deal_id']}: {rejection_reason}",
                     json.dumps([f"human rejection {approval_id}"])),
                )
        return DomainEvent("approval.decided", f"approval-decision:{approval_id}", {"approval_id": approval_id, "approved": approved})

