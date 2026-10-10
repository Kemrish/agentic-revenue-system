from datetime import datetime, timedelta, timezone

from revenue_system.skills.tracking import check_stall


def test_stall_is_detected_after_sla():
    result = check_stall("outreach", datetime.now(timezone.utc) - timedelta(days=8), 7)
    assert result.stalled is True

