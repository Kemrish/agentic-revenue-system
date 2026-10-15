import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from revenue_system.adapters.db import SQLiteStore
from revenue_system.governance.provider_security import (
    hubspot_valid,
    reply_token,
    resend_valid,
)
from revenue_system.orchestration.events import DomainEvent
from revenue_system.orchestration.provider_events import ProviderEventResolver
from revenue_system.settings import Settings
from revenue_system.webhooks import app


def test_native_hubspot_signed_batch_is_durable_and_idempotent(monkeypatch):
    monkeypatch.setenv("HUBSPOT_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("PUBLIC_WEBHOOK_URL", "https://revenue.example.com")
    body = json.dumps([{"subscriptionType": "contact.creation", "objectId": 42, "portalId": 1, "subscriptionId": 9, "eventId": 123}]).encode()
    stamp = str(int(time.time() * 1000))
    signed = b"POSThttps://revenue.example.com/providers/hubspot" + body + stamp.encode()
    signature = base64.b64encode(hmac.digest(b"test-secret", signed, "sha256")).decode()
    headers = {"x-hubspot-signature-v3": signature, "x-hubspot-request-timestamp": stamp}
    with TestClient(app) as client:
        assert client.post("/providers/hubspot", content=body, headers=headers).json()["accepted"] == 1
        assert client.post("/providers/hubspot", content=body, headers=headers).json()["duplicates"] == 1
        assert client.post("/providers/hubspot", content=body + b" ", headers=headers).status_code == 401
    store = SQLiteStore(Settings().database_url)
    assert store.pending_events()[0]["event_type"] == "provider.hubspot.contact"
    store.connection.close()


def test_replayed_timestamps_and_forged_signatures_fail():
    assert not hubspot_valid(b"[]", "bad", "0", "key", "https://example.com")
    key = base64.b64encode(b"secret").decode()
    assert not resend_valid(b"{}", "id", "0", "bad", "whsec_" + key)
    assert not resend_valid(b"{}", "id", str(int(time.time())), "bad", "not-base64!")


def test_native_resend_signature_and_idempotence(monkeypatch):
    secret = b"test-secret"
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", "whsec_" + base64.b64encode(secret).decode())
    stamp = str(int(time.time()))
    body = b'{"type":"email.received","data":{"email_id":"email-1"}}'
    signature = base64.b64encode(hmac.digest(secret, b"message-1." + stamp.encode() + b"." + body, "sha256")).decode()
    headers = {"svix-id": "message-1", "svix-timestamp": stamp, "svix-signature": "v1," + signature}
    with TestClient(app) as client:
        assert client.post("/providers/resend", content=body, headers=headers).json()["accepted"] == 1
        assert client.post("/providers/resend", content=body, headers=headers).json()["duplicates"] == 1
        headers["svix-signature"] = "forged"
        assert client.post("/providers/resend", content=body, headers=headers).status_code == 401


def test_fireflies_v2_retry_timestamp_is_not_an_event_identity(monkeypatch):
    monkeypatch.setenv("FIREFLIES_WEBHOOK_SECRET", "test-secret")
    with TestClient(app) as client:
        for index in range(2):
            body = json.dumps({"event": "meeting.transcribed", "timestamp": int(time.time()*1000) + index,
                               "meeting_id": "t1", "client_reference_id": "d1"}).encode()
            sig = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
            result = client.post("/providers/fireflies", content=body, headers={"x-hub-signature": sig})
            assert result.json()["accepted"] == (1 if index == 0 else 0)


def test_dropbox_multipart_ack_and_unknown_event(monkeypatch):
    monkeypatch.setenv("ESIGN_API_KEY", "test-key")
    event = {"event_time": "123", "event_type": "account_confirmed"}
    event["event_hash"] = hmac.new(b"test-key", b"123account_confirmed", hashlib.sha256).hexdigest()
    with TestClient(app) as client:
        response = client.post("/providers/dropbox-sign", files={"json": (None, json.dumps({"event": event}))})
        assert response.status_code == 200 and response.text == "Hello API Event Received"
        event["event_hash"] = "forged"
        assert client.post("/providers/dropbox-sign", files={"json": (None, json.dumps({"event": event}))}).status_code == 401


@pytest.mark.asyncio
async def test_resolver_fetches_hubspot_evidence_without_invented_scores(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'provider.db'}")
    class CRM:
        async def get_contact(self, key, fields):
            return {"company": "Account", "firstname": "Amina", "email": "a@example.com", "ars_segment": "brand", "ars_fit": "80"}
    container = SimpleNamespace(store=store, settings=Settings(), crm=CRM())
    result = await ProviderEventResolver(container).resolve(DomainEvent("provider.hubspot.contact", "e1", {"contact_id": "42"}))
    assert result.event_type == "lead.created" and result.payload["lead_id"] == "hubspot-contact-42"
    assert result.payload["fit"] == 80 and result.payload["intent"] == 0
    store.connection.close()


@pytest.mark.asyncio
async def test_esign_completion_requires_matching_sent_request_and_remote_confirmation(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'provider.db'}")
    from revenue_system.domain.models import Action, ActionType
    store.add_outbox_once("contract", Action(ActionType.SEND_CONTRACT, "d1", {}))
    store.mark_outbox_sent("contract", "signature-1")
    class ESign:
        complete = False
        async def verify_completed(self, provider_id):
            return self.complete
    esign = ESign()
    resolver = ProviderEventResolver(SimpleNamespace(store=store, settings=Settings(), esign=esign))
    event = DomainEvent("provider.esign.completed", "e1", {"provider_id": "signature-1"})
    with pytest.raises(ValueError, match="not verified"):
        await resolver.resolve(event)
    esign.complete = True
    assert (await resolver.resolve(event)).payload["deal_id"] == "d1"
    with pytest.raises(ValueError):
        await resolver.resolve(DomainEvent(event.event_type, "e2", {"provider_id": "unknown"}))
    store.connection.close()


@pytest.mark.asyncio
async def test_mail_reply_requires_opaque_thread_and_matching_sender(tmp_path):
    from revenue_system.domain.models import Action, ActionType
    store = SQLiteStore(f"sqlite:///{tmp_path / 'reply.db'}")
    store.add_outbox_once("mail-1", Action(ActionType.SEND_FIRST_TOUCH, "d1", {"recipient": "a@example.com"}))
    store.mark_outbox_sent("mail-1", "provider-1")
    s = Settings(mail_thread_secret="test-secret", mail_reply_domain="inbound.example.com")
    class Mail:
        sender = "a@example.com"
        async def get_received(self, key):
            return {"from": self.sender, "to": [f"reply+{reply_token('mail-1', s.mail_thread_secret)}@{s.mail_reply_domain}"], "text": "Interested"}
    mail = Mail()
    resolver = ProviderEventResolver(SimpleNamespace(store=store, settings=s, mail=mail))
    event = DomainEvent("provider.resend.reply", "e1", {"email_id": "email-1"})
    assert (await resolver.resolve(event)).payload["deal_id"] == "d1"
    mail.sender = "stranger@example.com"
    with pytest.raises(ValueError, match="correlated"):
        await resolver.resolve(event)
    store.connection.close()
