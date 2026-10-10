from fastapi import FastAPI, Header, HTTPException, Request

from revenue_system.adapters.db import SQLiteStore
from revenue_system.orchestration.events import DomainEvent
from revenue_system.orchestration.worker import EventWorker

app = FastAPI(title="Agentic Revenue System Webhooks")
_store = SQLiteStore("sqlite:///:memory:")
_worker = EventWorker(_store)


@app.post("/webhooks/hubspot")
async def hubspot_webhook(request: Request, x_event_id: str | None = Header(default=None)) -> dict[str, str]:
    body = await request.json()
    event_id = x_event_id or body.get("eventId") or body.get("objectId")
    if not event_id:
        raise HTTPException(status_code=400, detail="missing event id")
    accepted = _worker.ingest(DomainEvent("lead.created", f"hubspot:{event_id}", body))
    return {"status": "accepted" if accepted else "duplicate"}


@app.post("/webhooks/fireflies")
async def fireflies_webhook(request: Request, x_event_id: str | None = Header(default=None)) -> dict[str, str]:
    body = await request.json()
    event_id = x_event_id or body.get("transcriptId")
    if not event_id:
        raise HTTPException(status_code=400, detail="missing transcript id")
    accepted = _worker.ingest(DomainEvent("transcript.ready", f"fireflies:{event_id}", body))
    return {"status": "accepted" if accepted else "duplicate"}

