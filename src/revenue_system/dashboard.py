"""Local operator dashboard: review proposals, decide, and trace delivery."""

import asyncio
import json
from uuid import uuid4
from contextlib import contextmanager
from pathlib import Path

import secrets
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .adapters.db import SQLiteStore
from .container import build_container
from .orchestration.orchestrator import DealOrchestrator
from .orchestration.worker import EventWorker
from .demo_api import router as demo_router
from .domain.models import Action, ActionType
from .governance.approvals import ApprovalService
from .governance.policy import PolicyEngine
from .orchestration.delivery import OutboxDeliveryService
from .segments.registry import PackRegistry
from .settings import Settings

_basic = HTTPBasic(auto_error=False)


def operator(request: Request, credentials: HTTPBasicCredentials | None = Depends(_basic)) -> str:
    """HTTP Basic sign-in when DASHBOARD_PASSWORD is set; returns the audit actor."""
    settings = Settings()
    if request.url.path == "/healthz":
        return "human"
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.url.netloc:
            raise HTTPException(403, "Cross-origin operator actions are refused.")
    if not settings.dashboard_password:
        if settings.app_env.lower() == "production":
            raise HTTPException(503, "DASHBOARD_PASSWORD is required in production.")
        return "human"
    valid = credentials is not None and (
        secrets.compare_digest(credentials.username.encode(), settings.dashboard_username.encode())
        and secrets.compare_digest(credentials.password.encode(), settings.dashboard_password.encode()))
    if not valid:
        raise HTTPException(401, "Sign in required.", headers={"WWW-Authenticate": "Basic"})
    return f"human:{credentials.username}"


app = FastAPI(title="Agentic Revenue System Dashboard", dependencies=[Depends(operator)])
ASSETS = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=ASSETS, check_dir=False), name="static")
app.include_router(demo_router)
_delivery_lock = asyncio.Lock()


class RejectionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class RecipientRequest(BaseModel):
    recipient: str = Field(min_length=3, max_length=254)


class KillSwitchRequest(BaseModel):
    enabled: bool


class LessonStatusRequest(BaseModel):
    status: str = Field(pattern="^(active|retired|proposed)$")


class LessonRequest(BaseModel):
    statement: str = Field(min_length=3, max_length=1000)
    segment: str = "global"
    evidence: str = Field(default="operator", max_length=500)


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
            flags = payload.get("flags", [])
            deals.append({"id": row["id"], "company": row["company_name"],
                          "contact": row["contact_name"], "segment": row["segment"],
                          "score": score.get("total", 0), "tier": score.get("tier", "-"),
                          "stage": row["stage"], "score_reason": score.get("reason", ""),
                          "fields": payload.get("fields", {}), "flags": flags})
        approvals = [action_details(store, row) for row in store.pending_approvals()]
        history = [action_details(store, row) for row in rows(store,
                   "SELECT * FROM approvals WHERE status!='pending' ORDER BY created_at DESC, id")]
        outbox = [action_details(store, row) for row in rows(store,
                  "SELECT * FROM outbox ORDER BY created_at DESC, id")]
        audit = rows(store, "SELECT * FROM audit_log ORDER BY id DESC LIMIT 500")
        lessons = [row | {"evidence": json.loads(row["evidence"])} for row in rows(store,
                   "SELECT * FROM lessons ORDER BY CASE status WHEN 'proposed' THEN 0 WHEN 'active' THEN 1 ELSE 2 END, created_at DESC")]
        decisions = {row["action"]: row["n"] for row in rows(store,
                     "SELECT action, COUNT(*) n FROM audit_log WHERE actor='policy' GROUP BY action")}
        count = lambda query: store.connection.execute(query).fetchone()[0]
        return {
            "runtime": {"provider": settings.llm_provider, "mode": settings.runtime_mode,
                        "mail_mode": settings.mail_mode, "live_side_effects_enabled": settings.live_side_effects_enabled,
                        "kill_switch": store.flag_enabled("global_kill_switch"),
                        "demo_enabled": settings.demo_enabled and settings.app_env.lower() != "production",
                        "allowed_recipients": [v.strip() for v in settings.mail_allowed_recipients.split(",") if v.strip()]},
            "metrics": {"deals": len(deals), "pending_approvals": len(approvals),
                        "rejected_approvals": store.rejected_approvals_count(),
                        "outbox_pending": count("SELECT COUNT(*) FROM outbox WHERE status='pending'"),
                        "audit_events": count("SELECT COUNT(*) FROM audit_log")},
            "deals": deals, "approvals": approvals, "approval_history": history,
            "outbox": outbox, "audit": audit, "lessons": lessons,
            "stage_counts": {row["stage"]: row["n"] for row in rows(store, "SELECT stage, COUNT(*) n FROM deals GROUP BY stage")},
            "policy_decisions": decisions,
            "health": store.health() | {"stalled_deals": sum("stalled" in d["flags"] for d in deals)},
            "failed_events": rows(store, "SELECT id,event_type,status,attempts,last_error,next_attempt_at FROM events WHERE status='dead' ORDER BY created_at DESC LIMIT 100"),
            "scenarios": [
                {"name": "Automatic", "decision": "AUTO", "reason": "Permitted actions enter the outbox without human review."},
                {"name": "Human approval", "decision": "REQUIRE_APPROVAL", "reason": "Tier-A first touch and commercial actions need review."},
                {"name": "Denied", "decision": "DENY", "reason": "Unsafe or injection-flagged actions are blocked."},
                {"name": "Emergency stop", "decision": "KILL_SWITCH", "reason": "The global switch pauses routing and delivery."},
            ],
        }


@app.get("/healthz")
def healthz():
    with dashboard_store() as (_, store):
        return {"status": "ok", "kill_switch": store.flag_enabled("global_kill_switch"), "queues": store.health()}


@app.post("/api/approvals/{approval_id}/approve")
def approve(approval_id: str, actor: str = Depends(operator)):
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
            ApprovalService(store).decide(approval_id, True, actor=actor)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"message": "Approved. The reviewed action is queued; delivery is a separate step."}


@app.post("/api/approvals/{approval_id}/reject")
def reject(approval_id: str, payload: RejectionRequest, actor: str = Depends(operator)):
    with dashboard_store() as (_, store):
        reason = payload.reason.strip()
        if not reason:
            raise HTTPException(400, "A rejection reason is required.")
        if not store.get_approval(approval_id):
            raise HTTPException(404, "Approval not found.")
        try:
            ApprovalService(store).decide(approval_id, False, reason, actor=actor)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"message": "Rejected. Reason recorded and a proposed lesson saved for review."}


@app.patch("/api/{collection}/{item_id}/recipient")
def set_recipient(collection: str, item_id: str, request: RecipientRequest, actor: str = Depends(operator)):
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
            store.connection.execute(f"UPDATE {collection} SET payload=?, next_attempt_at=NULL WHERE id=? AND status='pending'" if collection == "outbox" else f"UPDATE {collection} SET payload=? WHERE id=? AND status='pending'",
                                     (json.dumps(payload), item_id))
            store.connection.execute(
                "INSERT INTO audit_log(deal_id,actor,action,detail,created_at) VALUES(?,?,?,?,datetime('now'))",
                (row["deal_id"], actor, "recipient_set", f"{collection}:{item_id} recipient={recipient}"))
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
            service = OutboxDeliveryService(container.store, container.mail, esign=container.esign,
                                            max_attempts=Settings().max_delivery_attempts,
                                            lease_seconds=Settings().queue_lease_seconds,
                                            retry_base_seconds=Settings().retry_base_seconds)
            delivered = await service.deliver_pending(continue_on_error=True)
            # Apply delivery outcomes to deal stages now; agent-backed events stay with the worker.
            await EventWorker(container.store).run_once(DealOrchestrator(container.store), {"action.delivered"})
            return {"message": f"Delivered {len(delivered)} action(s); {len(service.failures)} failed.",
                    "delivered": delivered, "failures": service.failures}
        finally:
            container.store.connection.close()


@app.post("/api/kill-switch")
def set_kill_switch(request: KillSwitchRequest, actor: str = Depends(operator)):
    with dashboard_store() as (_, store):
        store.set_flag("global_kill_switch", request.enabled)
        store.audit(actor, "KILL_SWITCH" if request.enabled else "kill_switch_released",
                    "Emergency stop enabled from dashboard" if request.enabled else "Operations resumed from dashboard")
        return {"message": "Emergency stop is active. Routing and delivery are paused." if request.enabled
                else "Operations resumed. Queued work can be delivered again."}


@app.post("/api/lessons")
def add_lesson(request: LessonRequest, actor: str = Depends(operator)):
    with dashboard_store() as (_, store):
        lesson_id = f"lesson-{uuid4().hex[:8]}"
        store.save_lesson(lesson_id, request.segment, request.statement.strip(), [request.evidence])
        store.audit(actor, "lesson_proposed", f"{lesson_id}: {request.statement.strip()}")
        return {"message": "Saved as a proposed lesson. Promote it in Lessons before agents can use it.", "id": lesson_id}


@app.post("/api/lessons/{lesson_id}/status")
def set_lesson_status(lesson_id: str, request: LessonStatusRequest, actor: str = Depends(operator)):
    with dashboard_store() as (_, store):
        with store.connection:
            updated = store.connection.execute("UPDATE lessons SET status=? WHERE id=?", (request.status, lesson_id))
            if updated.rowcount != 1:
                raise HTTPException(404, "Lesson not found.")
            store.connection.execute(
                "INSERT INTO audit_log(deal_id,actor,action,detail,created_at) VALUES(NULL,?,?,?,datetime('now'))",
                (actor, f"lesson_{request.status}", lesson_id))
        verb = {"active": "Promoted. Outreach will retrieve it on the next run.", "retired": "Retired. Agents will no longer retrieve it.",
                "proposed": "Moved back to proposed."}[request.status]
        return {"message": verb}


@app.post("/api/queues/{queue}/{item_id}/retry")
def retry_queue_item(queue: str, item_id: str, actor: str = Depends(operator)):
    if queue not in {"events", "outbox"}:
        raise HTTPException(404, "Queue not found.")
    with dashboard_store() as (_, store):
        if not store.retry_failed(queue, item_id, actor):
            raise HTTPException(409, "Only dead events or failed deliveries can be retried.")
        return {"message": "Retry scheduled. The original idempotency key is retained."}
