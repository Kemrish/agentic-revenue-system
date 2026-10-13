from fastapi.testclient import TestClient

from revenue_system.dashboard import app


def test_dashboard_renders_and_exposes_policy_scenarios():
    client = TestClient(app)
    assert client.get("/").status_code == 200
    payload = client.get("/api/overview").json()
    assert {item["decision"] for item in payload["scenarios"]} == {"AUTO", "REQUIRE_APPROVAL", "DENY", "KILL_SWITCH"}
