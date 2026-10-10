from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Action, ActionType
from revenue_system.governance.approvals import ApprovalService
from revenue_system.orchestration.outbox import OutboxWorker


def test_approved_action_enters_outbox(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'outbox.db'}")
    service = ApprovalService(store)
    service.request("a1", Action(ActionType.SEND_FIRST_TOUCH, "d1", {"body": "hello"}))
    service.decide("a1", True)
    assert OutboxWorker(store).pending()[0]["deal_id"] == "d1"

