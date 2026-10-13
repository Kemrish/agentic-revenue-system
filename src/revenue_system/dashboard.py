"""Local operator dashboard: review proposals, decide, and trace delivery."""

import asyncio
import json
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .adapters.db import SQLiteStore
from .container import build_container
from .domain.models import Action, ActionType
from .governance.approvals import ApprovalService
from .governance.policy import PolicyEngine
from .orchestration.delivery import OutboxDeliveryService
from .segments.registry import PackRegistry
from .settings import Settings

app = FastAPI(title="Agentic Revenue System Dashboard")
ASSETS = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=ASSETS, check_dir=False), name="static")
_delivery_lock = asyncio.Lock()


class RejectionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class RecipientRequest(BaseModel):
    recipient: str = Field(min_length=3, max_length=254)


@contextmanager
def dashboard_store():
    settings = Settings()
    store = SQLiteStore(settings.database_url)
    try:
        yield settings, store
    finally:
        store.connection.close()


def rows(store, query, params=()):
    return [dict(row) for row in store.connection.execute(query, params)]


def action_details(store, row):
    item = dict(row)
    item["payload"] = json.loads(item["payload"])
    deal = store.get_deal(item["deal_id"])
    item.update(company=deal.company_name if deal else item["deal_id"],
                contact=deal.contact_name if deal else "", segment=deal.segment if deal else "",
                tier=deal.score.tier.value if deal and deal.score else "-",
                score=deal.score.total if deal and deal.score else 0,
                score_reason=deal.score.reason if deal and deal.score else "Score unavailable")
    item["policy_reason"] = "Approval required by the default policy rule."
    if deal:
        decision = PolicyEngine().evaluate(
            Action(ActionType(item["action_type"]), deal.id, item["payload"]),
            deal, PackRegistry(Path("packs")).get(deal.segment),
        )
        item["policy_reason"] = decision.reason
        item["rule_id"] = decision.rule_id
    return item


def validate_recipient(recipient, settings):
    recipient = recipient.strip()
    if "@" not in recipient or any(c.isspace() for c in recipient):
        raise HTTPException(400, "Enter a valid recipient email address.")
    if settings.runtime_mode == "live" and settings.mail_mode == "live":
        allowed = {value.strip() for value in settings.mail_allowed_recipients.split(",") if value.strip()}
        if recipient not in allowed:
            raise HTTPException(400, "Recipient must be in MAIL_ALLOWED_RECIPIENTS for live delivery.")
    return recipient


@app.get("/")
def index():
    return FileResponse(ASSETS / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/overview")
def overview():
    with dashboard_store() as (settings, store):
        deals = []
        for row in rows(store, "SELECT * FROM deals ORDER BY updated_at DESC, id"):
            payload = json.loads(row["payload"])
            score = payload.get("score") or {}
            deals.append({"id": row["id"], "company": row["company_name"],
                          "contact": row["contact_name"], "segment": row["segment"],
                          "score": score.get("total", 0), "tier": score.get("tier", "-"),
                          "stage": row["stage"], "score_reason": score.get("reason", ""),
                          "fields": payload.get("fields", {})})
        approvals = [action_details(store, row) for row in store.pending_approvals()]
        history = [action_details(store, row) for row in rows(store,
                   "SELECT * FROM approvals WHERE status!='pending' ORDER BY created_at DESC, id")]
        outbox = [action_details(store, row) for row in rows(store,
                  "SELECT * FROM outbox ORDER BY created_at DESC, id")]
        audit = rows(store, "SELECT * FROM audit_log ORDER BY id DESC LIMIT 500")
        count = lambda query: store.connection.execute(query).fetchone()[0]
        return {
            "runtime": {"provider": settings.llm_provider, "mode": settings.runtime_mode,
                        "mail_mode": settings.mail_mode, "live_side_effects_enabled": settings.live_side_effects_enabled,
                        "kill_switch": store.flag_enabled("global_kill_switch"),
                        "allowed_recipients": [v.strip() for v in settings.mail_allowed_recipients.split(",") if v.strip()]},
            "metrics": {"deals": len(deals), "pending_approvals": len(approvals),
                        "rejected_approvals": store.rejected_approvals_count(),
                        "outbox_pending": count("SELECT COUNT(*) FROM outbox WHERE status='pending'"),
                        "audit_events": count("SELECT COUNT(*) FROM audit_log")},
            "deals": deals, "approvals": approvals, "approval_history": history,
            "outbox": outbox, "audit": audit,
            "scenarios": [
                {"name": "Automatic", "decision": "AUTO", "reason": "Permitted actions enter the outbox without human review."},
                {"name": "Human approval", "decision": "REQUIRE_APPROVAL", "reason": "Tier-A first touch and commercial actions need review."},
                {"name": "Denied", "decision": "DENY", "reason": "Unsafe or injection-flagged actions are blocked."},
                {"name": "Emergency stop", "decision": "KILL_SWITCH", "reason": "The global switch pauses routing and delivery."},
            ],
        }


@app.post("/api/approvals/{approval_id}/approve")
def approve(approval_id: str):
    with dashboard_store() as (settings, store):
        row = store.get_approval(approval_id)
        if not row:
            raise HTTPException(404, "Approval not found.")
        if row["status"] != "pending":
            raise HTTPException(409, "This approval has already been decided. Refresh to see its status.")
        payload = json.loads(row["payload"])
        if payload.get("unsafe") or payload.get("injection_detected"):
            raise HTTPException(400, "Unsafe actions cannot be approved.")
        if row["action_type"] in {"send_first_touch", "send_follow_up"}:
            if not payload.get("recipient"):
                raise HTTPException(400, "Set and review a recipient before approving this message.")
            validate_recipient(payload["recipient"], settings)
            if not payload.get("subject") or not payload.get("body"):
                raise HTTPException(400, "A subject and message body are required.")
        try:
            ApprovalService(store).decide(approval_id, True)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"message": "Approved. The reviewed action is queued; delivery is a separate step."}


@app.post("/api/approvals/{approval_id}/reject")
def reject(approval_id: str, payload: RejectionRequest):
    with dashboard_store() as (_, store):
        reason = payload.reason.strip()
        if not reason:
            raise HTTPException(400, "A rejection reason is required.")
        if not store.get_approval(approval_id):
            raise HTTPException(404, "Approval not found.")
        try:
            ApprovalService(store).decide(approval_id, False, reason)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"message": "Rejected. Reason recorded and a proposed lesson saved for review."}


@app.patch("/api/{collection}/{item_id}/recipient")
def set_recipient(collection: str, item_id: str, request: RecipientRequest):
    if collection not in {"approvals", "outbox"}:
        raise HTTPException(404, "Action collection not found.")
    with dashboard_store() as (settings, store):
        recipient = validate_recipient(request.recipient, settings)
        with store.connection:
            row = store.connection.execute(f"SELECT * FROM {collection} WHERE id=?", (item_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Action not found.")
            if row["status"] != "pending":
                raise HTTPException(409, "Only pending actions can be updated.")
            if row["action_type"] not in {"send_first_touch", "send_follow_up"}:
                raise HTTPException(400, "This action does not use an email recipient.")
            payload = json.loads(row["payload"])
            if collection == "outbox" and payload.get("recipient"):
                raise HTTPException(409, "A queued recipient cannot be changed after review.")
            payload["recipient"] = recipient
            store.connection.execute(f"UPDATE {collection} SET payload=? WHERE id=? AND status='pending'",
                                     (json.dumps(payload), item_id))
            store.connection.execute(
                "INSERT INTO audit_log(deal_id,actor,action,detail,created_at) VALUES(?,?,?,?,datetime('now'))",
                (row["deal_id"], "human", "recipient_set", f"{collection}:{item_id} recipient={recipient}"))
        return {"message": "Recipient saved. Review the message before continuing."}


@app.post("/api/outbox/deliver")
async def deliver():
    if _delivery_lock.locked():
        raise HTTPException(409, "Delivery is already running. Wait for it to finish.")
    async with _delivery_lock:
        container = build_container(Settings())
        try:
            if container.store.flag_enabled("global_kill_switch"):
                raise HTTPException(409, "Emergency stop is active. Queued actions remain pending.")
            service = OutboxDeliveryService(container.store, container.mail, esign=container.esign)
            delivered = await service.deliver_pending(continue_on_error=True)
            return {"message": f"Delivered {len(delivered)} action(s); {len(service.failures)} failed.",
                    "delivered": delivered, "failures": service.failures}
        finally:
            container.store.connection.close()
