"""Operator commands for the durable revenue workflow."""

import typer
import asyncio
import json
from pathlib import Path
from .container import agent_runner, build_container
from .governance.approvals import ApprovalService
from .orchestration.delivery import OutboxDeliveryService
from .orchestration.orchestrator import DealOrchestrator
from .orchestration.worker import EventWorker
from .segments.registry import PackRegistry
from .dashboard import app as dashboard_app
from .adapters.db import SQLiteStore
from .orchestration.events import DomainEvent
from .settings import Settings
from .governance.ingress import LeadInput

app = typer.Typer(help="Agentic Revenue System CLI")


@app.command("validate-packs")
def validate_packs() -> None:
    """Validate all configured segment packs."""
    packs = PackRegistry(Path("packs"))
    for pack in packs.all():
        typer.echo(f"valid: {pack.segment}")
    typer.echo(f"validated {len(packs.all())} segment packs")


@app.command()
def kill_switch(enabled: bool = typer.Option(..., "--enabled/--disabled")) -> None:
    """Enable or disable the global action kill switch."""
    build_container().store.set_flag("global_kill_switch", enabled)
    typer.echo(f"global kill switch={'on' if enabled else 'off'}")


@app.command()
def audit(deal_id: str = typer.Argument(...)) -> None:
    """Display audit records for a deal."""
    store = build_container().store
    rows = store.connection.execute("SELECT actor, action, detail, created_at FROM audit_log WHERE deal_id=? ORDER BY id", (deal_id,))
    for row in rows:
        typer.echo(f"{row['created_at']} {row['actor']} {row['action']}: {row['detail']}")


approvals_app = typer.Typer(help="Manage human approvals")
app.add_typer(approvals_app, name="approvals")


@approvals_app.command("list")
def list_approvals() -> None:
    for row in build_container().store.pending_approvals():
        typer.echo(f"{row['id']} deal={row['deal_id']} action={row['action_type']}")


@approvals_app.command("approve")
def approve(approval_id: str) -> None:
    event = ApprovalService(build_container().store).decide(approval_id, True, actor="human:cli")
    typer.echo(f"approved: {event.payload['approval_id']}; action queued in outbox")


@approvals_app.command("reject")
def reject(approval_id: str, reason: str = typer.Option(..., "--reason", prompt="Why are you rejecting this approval?")) -> None:
    event = ApprovalService(build_container().store).decide(approval_id, False, reason, actor="human:cli")
    typer.echo(f"rejected: {event.payload['approval_id']}")


@approvals_app.command("deliver")
def deliver_approved() -> None:
    """Deliver approved outbox actions through configured live adapters."""
    container = build_container()
    try:
        service = OutboxDeliveryService(container.store, container.mail, esign=container.esign,
                                        max_attempts=container.settings.max_delivery_attempts,
                                        lease_seconds=container.settings.queue_lease_seconds,
                                        retry_base_seconds=container.settings.retry_base_seconds)
        delivered = asyncio.run(service.deliver_pending(continue_on_error=True))
        asyncio.run(EventWorker(container.store).run_once(DealOrchestrator(container.store), {"action.delivered"}))
        for item in delivered:
            typer.echo(f"delivered: {item}")
        for failure in service.failures:
            typer.echo(f"failed: {failure['id']}: {failure['reason']}")
        if service.failures:
            raise typer.Exit(1)
    finally:
        container.store.connection.close()


@app.command()
def worker(once: bool = typer.Option(False, "--once", help="Process pending events once and exit."),
           deliver: bool = typer.Option(False, "--deliver", help="Also deliver permitted outbox actions using configured adapters.")) -> None:
    """Process webhook events, SLA timers, and delivery outcomes."""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    container = build_container()
    _, label = agent_runner(container.settings)
    orchestrator = DealOrchestrator(container.store, Path("packs"), container.runner)
    events = EventWorker(container.store, container.settings.max_event_attempts,
                        container.settings.queue_lease_seconds, container.settings.retry_base_seconds)
    delivery = OutboxDeliveryService(container.store, container.mail, esign=container.esign,
                                    max_attempts=container.settings.max_delivery_attempts,
                                    lease_seconds=container.settings.queue_lease_seconds,
                                    retry_base_seconds=container.settings.retry_base_seconds) if deliver else None
    typer.echo(f"worker started: runner={label} db={container.settings.database_url}")
    try:
        if once:
            typer.echo(str(asyncio.run(events.run_once(orchestrator))))
            if delivery is not None:
                typer.echo(f"delivered: {len(asyncio.run(delivery.deliver_pending(continue_on_error=True)))}")
                if delivery.failures:
                    raise typer.Exit(1)
            return
        asyncio.run(events.run_forever(orchestrator, container.settings.worker_poll_seconds, delivery=delivery))
    except KeyboardInterrupt:
        typer.echo("worker stopped")
    finally:
        container.store.connection.close()


@app.command()
def webhooks(host: str = typer.Option("127.0.0.1"), port: int = typer.Option(8001)) -> None:
    """Start the signed webhook receiver."""
    import uvicorn
    from .settings import Settings
    from .webhooks import app as webhook_app
    if not Settings().webhook_secret:
        raise typer.BadParameter("Set WEBHOOK_SECRET before starting the webhook receiver.")
    uvicorn.run(webhook_app, host=host, port=port)


@app.command()
def ui(host: str = typer.Option("127.0.0.1"), port: int = typer.Option(8000)) -> None:
    """Start the operator dashboard."""
    import uvicorn
    from .settings import Settings
    if (host not in {"127.0.0.1", "localhost", "::1"} or Settings().app_env.lower() == "production") and not Settings().dashboard_password:
        raise typer.BadParameter("Set DASHBOARD_PASSWORD before exposing the dashboard beyond localhost.")
    uvicorn.run(dashboard_app, host=host, port=port)


@app.command()
def health() -> None:
    """Display durable queue counts without contacting any provider."""
    store = SQLiteStore(Settings().database_url)
    try:
        typer.echo(json.dumps(store.health(), indent=2))
    finally:
        store.connection.close()


@app.command()
def ingest(file: Path = typer.Option(..., "--file", exists=True, readable=True)) -> None:
    """Import real leads from a JSON object or array; writes events, never sends mail."""
    data = json.loads(file.read_text(encoding="utf-8"))
    data = data if isinstance(data, list) else [data]
    leads = [LeadInput.model_validate({**row, "lead_id": str(row.get("lead_id") or row.get("id") or "")}) for row in data]
    registry = PackRegistry(Path("packs"))
    for lead in leads:
        registry.get(lead.segment)
    store = SQLiteStore(Settings().database_url)
    try:
        with store.transaction():
            accepted = sum(store.add_event_once(f"import:lead:{lead.lead_id}", "lead.created", lead.model_dump()) for lead in leads)
        typer.echo(f"accepted={accepted} duplicates={len(leads)-accepted}; run worker to process")
    finally:
        store.connection.close()


queues_app = typer.Typer(help="Inspect failed work and explicitly schedule recovery")
app.add_typer(queues_app, name="queues")


@queues_app.command("failed")
def failed_work() -> None:
    store = SQLiteStore(Settings().database_url)
    try:
        for table, status in (("events", "dead"), ("outbox", "failed")):
            for row in store.connection.execute(f"SELECT id,attempts,last_error FROM {table} WHERE status=?", (status,)):
                typer.echo(f"{table} {row['id']} attempts={row['attempts']} error={row['last_error']}")
    finally:
        store.connection.close()


@queues_app.command("retry")
def retry_work(queue: str, item_id: str) -> None:
    if queue not in {"events", "outbox"}:
        raise typer.BadParameter("queue must be events or outbox")
    store = SQLiteStore(Settings().database_url)
    try:
        if not store.retry_failed(queue, item_id, "human:cli"):
            raise typer.BadParameter("Only dead events or failed deliveries can be retried")
        typer.echo("retry scheduled")
    finally:
        store.connection.close()


if __name__ == "__main__":
    app()

