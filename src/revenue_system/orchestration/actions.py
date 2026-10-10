from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Action
from revenue_system.governance.policy import PolicyEngine
from revenue_system.segments.schema import SegmentPack


def route_action(store: SQLiteStore, action: Action, deal, pack: SegmentPack, policy: PolicyEngine | None = None) -> str:
    decision = (policy or PolicyEngine()).evaluate(action, deal, pack)
    store.audit("policy", decision.decision, f"{decision.rule_id}: {decision.reason}", deal.id)
    if decision.decision == "AUTO":
        store.add_outbox_once(f"{action.action_type.value}:{deal.id}", action)
    elif decision.decision == "REQUIRE_APPROVAL":
        store.add_approval(f"approval:{action.action_type.value}:{deal.id}", action)
    return decision.decision

