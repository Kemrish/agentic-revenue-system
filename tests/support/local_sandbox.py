"""Opt-in LOCAL simulation, excluded from the production wheel/container.

Run: python -m tests.support.local_sandbox --port 8010
All models/providers are test doubles. No credentials are loaded, no external
messages are sent, and data lives in an isolated ignored directory.
"""

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import threading
import time
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient

from revenue_system.adapters.db import SQLiteStore
from revenue_system.container import Container
from revenue_system.governance.provider_security import reply_token
from revenue_system.orchestration.orchestrator import DealOrchestrator
from revenue_system.orchestration.provider_events import ProviderEventResolver
from revenue_system.orchestration.worker import EventWorker
from revenue_system.settings import Settings
from revenue_system.skills.contracts import validate_contract
from tests.support.agents import AGENT_RESPONSES, FakeRunner

SECRET = "local-only-not-a-production-secret"
REPLY_DOMAIN = "inbound.sandbox.invalid"


def sandbox_settings(database: Path) -> Settings:
    return Settings(_env_file=None, app_env="sandbox", runtime_mode="test", claude_mode="test",
        database_url=f"sqlite:///{database.resolve().as_posix()}", llm_provider="SIMULATED - no real sends",
        dashboard_password="", webhook_secret=SECRET, hubspot_client_secret=SECRET,
        public_webhook_url="https://sandbox.invalid", resend_webhook_secret="whsec_" + base64.b64encode(SECRET.encode()).decode(),
        fireflies_webhook_secret=SECRET, esign_api_key=SECRET, mail_thread_secret=SECRET,
        mail_reply_domain=REPLY_DOMAIN, mail_allowed_recipients="contact@sandbox.invalid",
        hubspot_mode="test", mail_mode="test", fireflies_mode="test", esign_mode="test",
        anthropic_api_key="", openrouter_api_key="", hubspot_access_token="", mail_api_key="", fireflies_api_key="",
        live_side_effects_enabled=False, crm_sync_enabled=False, packs_root=None)


def sandbox_container(settings: Settings) -> Container:
    store = SQLiteStore(settings.database_url)
    class CRM:
        async def get_contact(self, contact_id, properties):
            if contact_id not in {"101", "102"}:
                raise ValueError("Only sandbox contacts 101/102 exist")
            return {"company": "Sandbox Brand" if contact_id == "101" else "Sandbox Publisher", "firstname": "Sandbox", "lastname": "Contact",
                    "email": "contact@sandbox.invalid", "ars_segment": "brand" if contact_id == "101" else "publisher",
                    "ars_fit": "90", "ars_intent": "80"}
    class Runner(FakeRunner):
        async def run(self, request, output_schema):
            if request.agent_name == "call_intelligence":
                fields = {"decision_maker": "Sandbox director", "budget": "1000", "timeline": "90 days",
                          "monthly_impressions": "75000000", "current_ssp": "Sandbox SSP"}
                return output_schema.model_validate(AGENT_RESPONSES["call_intelligence"] | {"qualification_fields": fields})
            return await super().run(request, output_schema)
    class Mail:
        async def send(self, recipient, subject, body, key):
            return "simulated-mail-" + hashlib.sha256(key.encode()).hexdigest()[:12]
        async def get_received(self, email_id):
            row = store.connection.execute("SELECT id FROM outbox WHERE deal_id=? AND action_type='send_first_touch' AND status='sent'", (email_id,)).fetchone()
            if not row:
                raise ValueError("Deliver the simulated first-touch message before emitting a reply")
            return {"from": "contact@sandbox.invalid", "to": [f"reply+{reply_token(row['id'], SECRET)}@{REPLY_DOMAIN}"], "text": "Interested. Let's schedule a meeting."}
    class Transcripts:
        async def get_transcript(self, transcript_id):
            return "Sandbox director confirmed budget 1000, 90 days, 75000000 impressions and current SSP."
    class ESign:
        async def send_for_signature(self, document, key):
            validate_contract(document)
            return "simulated-signature-" + hashlib.sha256(key.encode()).hexdigest()[:12]
        async def verify_completed(self, reference):
            return reference.startswith("simulated-signature-")
    return Container(settings, store, Runner(AGENT_RESPONSES), Mail(), Transcripts(), ESign(), CRM())


def emit(client: TestClient, kind: str, deal_id: str = ""):
    if kind == "leads":
        body = [{"subscriptionType": "contact.creation", "objectId": key, "portalId": 1, "subscriptionId": 1, "eventId": key} for key in (101, 102)]
        raw = json.dumps(body).encode()
        stamp = str(int(time.time() * 1000))
        sig = base64.b64encode(hmac.digest(SECRET.encode(), b"POSThttps://sandbox.invalid/providers/hubspot" + raw + stamp.encode(), "sha256")).decode()
        return client.post("/providers/hubspot", content=raw, headers={"x-hubspot-signature-v3": sig, "x-hubspot-request-timestamp": stamp})
    if kind == "reply":
        raw = json.dumps({"type": "email.received", "data": {"email_id": deal_id}}).encode()
        stamp, message_id = str(int(time.time())), "sandbox-reply-" + deal_id
        sig = base64.b64encode(hmac.digest(SECRET.encode(), message_id.encode() + b"." + stamp.encode() + b"." + raw, "sha256")).decode()
        return client.post("/providers/resend", content=raw, headers={"svix-id": message_id, "svix-timestamp": stamp, "svix-signature": "v1," + sig})
    if kind == "call":
        raw = json.dumps({"event": "meeting.transcribed", "timestamp": int(time.time()*1000), "meeting_id": "sandbox-call-" + deal_id, "client_reference_id": deal_id}).encode()
        return client.post("/providers/fireflies", content=raw, headers={"x-hub-signature": "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()})
    raise ValueError("Unknown sandbox event")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    root = Path(".local-sandbox")
    root.mkdir(exist_ok=True)
    settings = sandbox_settings(root / "sandbox.db")
    from revenue_system import dashboard, provider_webhooks, webhooks
    dashboard.Settings = webhooks.Settings = provider_webhooks.Settings = lambda: settings
    dashboard.build_container = lambda *_: sandbox_container(settings)
    client = TestClient(webhooks.app)
    emit(client, "leads").raise_for_status()

    @dashboard.app.post("/sandbox/{deal_id}/{kind}")
    def simulate_event(deal_id: str, kind: str):
        store = SQLiteStore(settings.database_url)
        try:
            deal = store.get_deal(deal_id)
            if not deal:
                raise HTTPException(404, "Unknown sandbox deal")
            if kind == "call":
                if deal.stage != "engaged":
                    raise HTTPException(409, "Emit and process the reply first")
                deal.fields["commercial_terms"] = {"legal_entity": deal.company_name, "budget": 1000,
                    "start_date": "2026-11-01", "end_date": "2027-01-31", "line_items": [{"name": "Sandbox service", "amount": 1000}]}
                store.save_deal(deal)
            if kind == "signed":
                row = store.connection.execute("SELECT provider_id FROM outbox WHERE deal_id=? AND action_type='send_contract' AND status='sent'", (deal_id,)).fetchone()
                if not row:
                    raise HTTPException(409, "Approve and deliver the simulated contract first")
                stamp, event_type = str(int(time.time())), "signature_request_all_signed"
                event = {"event_time": stamp, "event_type": event_type, "event_hash": hmac.new(SECRET.encode(), (stamp+event_type).encode(), hashlib.sha256).hexdigest()}
                result = client.post("/providers/dropbox-sign", files={"json": (None, json.dumps({"event": event, "signature_request": {"signature_request_id": row["provider_id"]}}))})
            elif kind in {"reply", "call"}:
                result = emit(client, kind, deal_id)
            else:
                raise HTTPException(404, "Use reply, call or signed")
            if result.is_error:
                raise HTTPException(result.status_code, "Simulated provider notification was rejected")
            return {"simulated": True, "queued": kind, "message": "Worker processes it on its next cycle; refresh the dashboard"}
        finally:
            store.connection.close()

    def run_worker():
        container = sandbox_container(settings)
        try:
            orchestrator = DealOrchestrator(container.store, runner=container.runner, providers=ProviderEventResolver(container))
            asyncio.run(EventWorker(container.store).run_forever(orchestrator, poll_seconds=1))
        finally:
            container.store.connection.close()
    threading.Thread(target=run_worker, daemon=True).start()
    print(f"LOCAL SIMULATION ONLY: http://127.0.0.1:{args.port} — no real models, credentials or external sends")
    import uvicorn
    uvicorn.run(dashboard.app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
