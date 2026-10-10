from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Action


class ApprovalService:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def request(self, approval_id: str, action: Action) -> None:
        self.store.add_approval(approval_id, action)
        self.store.audit("system", "approval_requested", action.action_type.value, action.deal_id)

