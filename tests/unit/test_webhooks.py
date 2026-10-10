from fastapi.testclient import TestClient

from revenue_system.webhooks import app


def test_webhook_is_idempotent():
    client = TestClient(app)
    payload = {"eventId": "evt-1", "objectId": "lead-1"}
    assert client.post("/webhooks/hubspot", json=payload).json()["status"] == "accepted"
    assert client.post("/webhooks/hubspot", json=payload).json()["status"] == "duplicate"

