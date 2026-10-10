from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Action, ActionType
from revenue_system.governance.approvals import ApprovalService


def test_approval_decision_creates_resume_event(tmp_path):
    service = ApprovalService(SQLiteStore(f"sqlite:///{tmp_path / 'approval.db'}"))
    service.request("a1", Action(ActionType.SEND_FIRST_TOUCH, "d1"))
    event = service.decide("a1", True)
    assert event.event_type == "approval.decided"
    assert event.payload["approved"] is True

