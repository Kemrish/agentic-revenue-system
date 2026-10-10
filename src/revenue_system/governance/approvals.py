from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Action
from revenue_system.orchestration.events import DomainEvent


class ApprovalService:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def request(self, approval_id: str, action: Action) -> None:
        self.store.add_approval(approval_id, action)
        self.store.audit("system", "approval_requested", action.action_type.value, action.deal_id)

    def decide(self, approval_id: str, approved: bool) -> DomainEvent:
        status = "approved" if approved else "rejected"
        self.store.connection.execute("UPDATE approvals SET status=? WHERE id=?", (status, approval_id))
        self.store.connection.commit()
        self.store.audit("human", f"approval_{status}", approval_id)
        if approved:
            row = self.store.get_approval(approval_id)
            if row:
                from revenue_system.domain.models import ActionType
                import json
                action = Action(ActionType(row["action_type"]), row["deal_id"], json.loads(row["payload"]))
                self.store.add_outbox_once(f"approved:{approval_id}", action)
        return DomainEvent("approval.decided", f"approval-decision:{approval_id}", {"approval_id": approval_id, "approved": approved})

