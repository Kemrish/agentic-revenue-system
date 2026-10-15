"""Provider-native ingress: authenticate locally, enqueue, acknowledge quickly."""

import json
from email.parser import BytesParser
from email.policy import default
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .adapters.db import SQLiteStore
from .governance.provider_security import (
    dropbox_valid,
    fresh,
    hubspot_valid,
    resend_valid,
)
from .governance.webhook_security import verify_hmac
from .settings import Settings

router = APIRouter()


async def bounded_body(request: Request, limit: int) -> bytes:
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, "Webhook body is too large")
        chunks.append(chunk)
    return b"".join(chunks)


def parse_dropbox(raw: bytes, content_type: str) -> dict:
    if content_type.startswith("multipart/form-data"):
        message = BytesParser(policy=default).parsebytes(b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw)
        values = [part.get_payload(decode=True) for part in message.iter_parts()
                  if part.get_param("name", header="content-disposition") == "json"]
        if len(values) != 1:
            raise ValueError("Expected one json form field")
        return json.loads(values[0])
    if content_type.startswith("application/x-www-form-urlencoded"):
        return json.loads(parse_qs(raw.decode(), strict_parsing=True)["json"][0])
    return json.loads(raw)


@router.post("/providers/{provider}")
async def native_webhook(provider: str, request: Request):
    if provider not in {"hubspot", "resend", "fireflies", "dropbox-sign"}:
        raise HTTPException(404, "Unknown provider")
    settings = Settings()
    secret = {"hubspot": settings.hubspot_client_secret, "resend": settings.resend_webhook_secret,
              "fireflies": settings.fireflies_webhook_secret, "dropbox-sign": settings.esign_api_key}[provider]
    if not secret:
        raise HTTPException(503, "Provider verification secret is not configured")
    raw = await bounded_body(request, settings.webhook_max_bytes)
    headers = request.headers
    if provider == "hubspot":
        if not settings.public_webhook_url:
            raise HTTPException(503, "PUBLIC_WEBHOOK_URL is required for HubSpot signature verification")
        # Dedicated canonical path; query parameters are not part of this contract.
        if request.url.query:
            raise HTTPException(400, "Webhook query parameters are not supported")
        valid = hubspot_valid(raw, headers.get("x-hubspot-signature-v3", ""),
                              headers.get("x-hubspot-request-timestamp", ""), secret,
                              settings.public_webhook_url.rstrip("/") + "/providers/hubspot")
    elif provider == "resend":
        valid = resend_valid(raw, headers.get("svix-id", ""), headers.get("svix-timestamp", ""),
                             headers.get("svix-signature", ""), secret)
    elif provider == "fireflies":
        valid = verify_hmac(raw, headers.get("x-hub-signature"), secret)
    else:
        valid = True  # Callback envelope must be parsed before event_hash verification.
    if not valid:
        raise HTTPException(401, "Invalid provider signature")
    try:
        body = parse_dropbox(raw, headers.get("content-type", "")) if provider == "dropbox-sign" else json.loads(raw)
        if provider == "dropbox-sign" and not dropbox_valid(body, secret):
            raise HTTPException(401, "Invalid callback event hash")
        events = []
        if provider == "hubspot":
            if not isinstance(body, list) or len(body) > 100:
                raise ValueError("Expected a bounded HubSpot event array")
            for item in body:
                if item["subscriptionType"] != "contact.creation":
                    continue
                contact_id = str(item["objectId"])
                if not contact_id.isdigit():
                    raise ValueError("Invalid contact ID")
                events.append((f"hubspot:{item['portalId']}:{item['subscriptionId']}:{item['eventId']}:{contact_id}",
                               "provider.hubspot.contact", {"contact_id": contact_id}))
        elif provider == "resend":
            if body["type"] == "email.received":
                events.append((f"resend:{headers['svix-id']}", "provider.resend.reply", {"email_id": body["data"]["email_id"]}))
        elif provider == "fireflies":
            if not fresh(body["timestamp"], 1000):
                raise HTTPException(401, "Expired Fireflies delivery timestamp")
            if body["event"] == "meeting.transcribed":
                events.append((f"fireflies:{body['meeting_id']}:{body.get('reprocessed_at', 'initial')}",
                               "provider.fireflies.transcript", {"transcript_id": body["meeting_id"],
                               "deal_id": body.get("client_reference_id"), "revision": body.get("reprocessed_at", 0)}))
        elif body["event"]["event_type"] == "signature_request_all_signed":
            reference = body["signature_request"]["signature_request_id"]
            events.append((f"dropbox-sign:completed:{reference}", "provider.esign.completed", {"provider_id": reference}))
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(422, "Invalid provider payload") from exc
    store = SQLiteStore(settings.database_url)
    try:
        with store.transaction():
            accepted = sum(store.add_event_once(key, kind, payload) for key, kind, payload in events)
    finally:
        store.connection.close()
    if provider == "dropbox-sign":
        return PlainTextResponse("Hello API Event Received")
    return {"accepted": accepted, "duplicates": len(events) - accepted}
