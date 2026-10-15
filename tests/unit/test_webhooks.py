import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from revenue_system.adapters.db import SQLiteStore
from revenue_system.webhooks import app

SECRET = "test-webhook-secret"


@pytest.fixture
def webhook_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'webhooks.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    return TestClient(app), url


def signed(payload: dict) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    return body, {"X-Signature": "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest(),
                  "Content-Type": "application/json"}


LEAD = {"eventId": "evt-1", "objectId": "lead-1", "segment": "brand", "company_name": "Example", "contact_name": "Amina"}


def test_webhook_is_idempotent_and_durable(webhook_db):
    client, url = webhook_db
    body, headers = signed(LEAD)
    assert client.post("/webhooks/hubspot", content=body, headers=headers).json()["status"] == "accepted"
    assert client.post("/webhooks/hubspot", content=body, headers=headers).json()["status"] == "duplicate"
    row = SQLiteStore(url).connection.execute("SELECT event_type, payload FROM events").fetchone()
    assert row["event_type"] == "lead.created"
    assert json.loads(row["payload"])["lead_id"] == "lead-1"


def test_unsigned_and_forged_webhooks_are_refused(webhook_db):
    client, _ = webhook_db
    body, _ = signed(LEAD)
    assert client.post("/webhooks/hubspot", content=body).status_code == 401
    assert client.post("/webhooks/hubspot", content=body, headers={"X-Signature": "sha256=forged"}).status_code == 401


def test_missing_secret_fails_closed(webhook_db, monkeypatch):
    client, _ = webhook_db
    monkeypatch.setenv("WEBHOOK_SECRET", "")
    body, headers = signed(LEAD)
    assert client.post("/webhooks/hubspot", content=body, headers=headers).status_code == 503


def test_payload_validation_and_sources(webhook_db):
    client, _ = webhook_db
    body, headers = signed({"messageId": "m1", "deal_id": "lead-1"})
    assert client.post("/webhooks/mail", content=body, headers=headers).status_code == 422
    body, headers = signed({"messageId": "m1", "deal_id": "lead-1", "text": "Interested"})
    assert client.post("/webhooks/mail", content=body, headers=headers).json()["event_id"] == "mail:m1"
    assert client.post("/webhooks/unknown", content=body, headers=headers).status_code == 404
    assert client.get("/healthz").json()["queues"]["events_pending"] == 1


@pytest.mark.parametrize("update", [
    {"fit":101}, {"fit":"not-a-number"}, {"company_name":["invalid"]}, {"segment":"unknown"},
])
def test_invalid_normalized_leads_are_refused_before_persistence(webhook_db, update):
    client, url = webhook_db
    body, headers = signed(LEAD | update)
    assert client.post("/webhooks/hubspot", content=body, headers=headers).status_code == 422
    store = SQLiteStore(url)
    try:
        assert store.health()["events_pending"] == 0
    finally:
        store.connection.close()


def test_unicode_signature_and_oversized_payload_fail_closed(webhook_db, monkeypatch):
    client, _ = webhook_db
    body, headers = signed(LEAD)
    headers["X-Signature"] = "sha256=invalid"
    assert client.post("/webhooks/hubspot", content=body, headers=headers).status_code == 401
    monkeypatch.setenv("WEBHOOK_MAX_BYTES", "1024")
    body, headers = signed(LEAD | {"description":"a"*2048})
    assert client.post("/webhooks/hubspot", content=body, headers=headers).status_code == 413


@pytest.mark.asyncio
async def test_persisted_webhook_runs_through_the_real_worker(webhook_db):
    from revenue_system.orchestration.orchestrator import DealOrchestrator
    from revenue_system.orchestration.worker import EventWorker
    from tests.support.agents import FakeRunner

    client, url = webhook_db
    body, headers = signed(LEAD | {"fit":90,"intent":80,"email":"review@example.com"})
    assert client.post("/webhooks/hubspot", content=body, headers=headers).status_code == 200
    # A separate connection represents a restarted receiver and worker process.
    store = SQLiteStore(url)
    try:
        assert (await EventWorker(store).run_once(DealOrchestrator(store, runner=FakeRunner())))["processed"] == 1
        assert store.get_approval("approval:send_first_touch:lead-1")["status"] == "pending"
    finally:
        store.connection.close()
