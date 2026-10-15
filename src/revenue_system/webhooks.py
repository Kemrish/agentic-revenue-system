"""Inbound webhooks: verify, validate, and persist as durable idempotent events.

Webhooks never do business work. They only record an event; the worker
processes it. Unsigned or unverifiable traffic is refused (fail closed).
"""

import json

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import ValidationError

from revenue_system.adapters.db import SQLiteStore
from revenue_system.governance.ingress import (
    LeadInput,
    ReplyInput,
    SignatureInput,
    TranscriptInput,
)
from revenue_system.governance.webhook_security import verify_hmac
from revenue_system.segments.registry import PackRegistry
from revenue_system.settings import Settings

from .provider_webhooks import router as provider_router

app = FastAPI(title="Agentic Revenue System Webhooks", docs_url=None, redoc_url=None, openapi_url=None)

app.include_router(provider_router)

# source -> (event type, body fields that may carry the provider event id, required payload fields)
SOURCES = {
    "hubspot": ("lead.created", ("eventId", "objectId", "lead_id"), ("segment", "company_name", "contact_name")),
    "mail": ("reply.received", ("messageId",), ("deal_id", "text")),
    "fireflies": ("transcript.ready", ("transcriptId",), ("deal_id", "transcript")),
    "esign": ("contract.signed", ("signatureRequestId", "eventId"), ("deal_id",)),
}
MODELS = {"hubspot": LeadInput, "mail": ReplyInput, "fireflies": TranscriptInput, "esign": SignatureInput}


async def accept(source: str, request: Request, event_id: str | None, signature: str | None) -> dict[str, str]:
    settings = Settings()
    if not settings.webhook_secret:
        raise HTTPException(503, "Webhook secret is not configured; unsigned traffic is refused.")
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > settings.webhook_max_bytes:
            raise HTTPException(413, "Webhook body exceeds the configured size limit.")
        chunks.append(chunk)
    raw = b"".join(chunks)
    if not verify_hmac(raw, signature, settings.webhook_secret):
        raise HTTPException(401, "invalid webhook signature")
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(400, "body must be JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a JSON object")
    event_type, id_fields, required = SOURCES[source]
    event_id = event_id or next((str(body[field]) for field in id_fields if body.get(field)), None)
    if not event_id:
        raise HTTPException(400, f"missing event id (X-Event-Id header or one of {list(id_fields)})")
    if source == "hubspot":
        body.setdefault("lead_id", str(body["objectId"]) if body.get("objectId") else None)
        required = required + ("lead_id",)
    missing = [field for field in required if not body.get(field)]
    if missing:
        raise HTTPException(422, f"missing required fields: {missing}")
    try:
        body = MODELS[source].model_validate(body).model_dump()
        if source == "hubspot":
            PackRegistry(settings.packs_root).get(body["segment"])
    except (ValidationError, KeyError) as exc:
        raise HTTPException(422, "Invalid event fields or unknown segment; check the normalized webhook contract.") from exc
    store = SQLiteStore(settings.database_url)
    try:
        accepted = store.add_event_once(f"{source}:{event_id}", event_type, body)
    finally:
        store.connection.close()
    return {"status": "accepted" if accepted else "duplicate", "event_id": f"{source}:{event_id}"}


@app.post("/webhooks/{source}")
async def webhook(source: str, request: Request, x_event_id: str | None = Header(default=None),
                  x_signature: str | None = Header(default=None)) -> dict[str, str]:
    if source not in SOURCES:
        raise HTTPException(404, "unknown webhook source")
    return await accept(source, request, x_event_id, x_signature)


@app.get("/healthz")
def healthz() -> dict:
    store = SQLiteStore(Settings().database_url)
    try:
        return {"status": "ok", "queues": store.health()}
    finally:
        store.connection.close()
