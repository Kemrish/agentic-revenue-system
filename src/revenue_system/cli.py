"""Operator commands for the durable revenue workflow."""

import asyncio
import json
from pathlib import Path

import typer

from .adapters.db import SQLiteStore
from .container import agent_runner, build_container
from .dashboard import app as dashboard_app
from .governance.approvals import ApprovalService
from .governance.ingress import LeadInput
from .orchestration.delivery import OutboxDeliveryService
from .orchestration.orchestrator import DealOrchestrator
from .orchestration.provider_events import ProviderEventResolver
from .orchestration.worker import EventWorker
from .segments.registry import PackRegistry
from .settings import Settings

app = typer.Typer(help="Agentic Revenue System CLI")


@app.command("validate-packs")
def validate_packs() -> None:
    """Validate all configured segment packs."""
    packs = PackRegistry(Settings().packs_root)
    for pack in packs.all():
        typer.echo(f"valid: {pack.segment}")
    typer.echo(f"validated {len(packs.all())} segment packs")


@app.command()
def kill_switch(enabled: bool = typer.Option(..., "--enabled/--disabled")) -> None:
    """Enable or disable the global action kill switch."""
    # Emergency control must work even if provider configuration is incomplete.
    store = SQLiteStore(Settings().database_url)
    try:
        store.set_flag("global_kill_switch", enabled)
        store.audit("human:cli", "kill_switch_changed", f"enabled={enabled}")
    finally:
        store.connection.close()
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
        service = OutboxDeliveryService(container.store, container.mail, esign=container.esign, crm=container.crm, settings=container.settings,
                                        max_attempts=container.settings.max_delivery_attempts,
                                        lease_seconds=container.settings.queue_lease_seconds,
                                        retry_base_seconds=container.settings.retry_base_seconds)
        delivered = asyncio.run(service.deliver_pending(continue_on_error=True))
        asyncio.run(EventWorker(container.store).run_once(DealOrchestrator(container.store, container.settings.packs_root,
                    crm_sync_enabled=container.settings.crm_sync_enabled), {"action.delivered"}))
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
    orchestrator = DealOrchestrator(container.store, container.settings.packs_root, container.runner, ProviderEventResolver(container), container.settings.crm_sync_enabled)
    events = EventWorker(container.store, container.settings.max_event_attempts,
                        container.settings.queue_lease_seconds, container.settings.retry_base_seconds)
    delivery = OutboxDeliveryService(container.store, container.mail, esign=container.esign, crm=container.crm, settings=container.settings,
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
    registry = PackRegistry(Settings().packs_root)
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


production_app = typer.Typer(help="Non-destructive production setup and local release checks")
app.add_typer(production_app, name="production")


@production_app.command("init")
def production_init(source: Path = typer.Option(Path(".env")), destination: Path = typer.Option(Path(".env.production")),
                    database: Path = typer.Option(Path("data/production.db"))) -> None:
    from .operations import initialize_production
    try:
        initialize_production(source, destination, database)
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo("Created a separate production profile and empty paused database. Existing credentials/data were preserved.")
    typer.echo("Review the ignored .env.production file privately. Set ARS_ENV_FILE before starting a NEW process; run production preflight.")


@production_app.command("preflight")
def production_preflight() -> None:
    from .operations import readiness
    report = readiness(Settings())
    typer.echo(json.dumps(report, indent=2))
    if not report["ready"]:
        raise typer.Exit(1)


@production_app.command("monitor")
def production_monitor(max_worker_age: int = typer.Option(600, min=30)) -> None:
    """Read-only monitor; nonzero exit is suitable for an external alerting job."""
    from .operations import operational_status
    result = operational_status(Settings(), max_worker_age)
    typer.echo(json.dumps(result))
    if not result["healthy"]:
        raise typer.Exit(1)


@production_app.command("backup")
def production_backup(destination: Path = typer.Option(...)) -> None:
    from .operations import database_path, snapshot
    snapshot(database_path(Settings().database_url), destination)
    typer.echo("Backup created and integrity checked. Protect it like the live database.")


@production_app.command("restore")
def production_restore(source: Path = typer.Option(..., exists=True), destination: Path = typer.Option(...)) -> None:
    from .operations import snapshot
    snapshot(source, destination)
    typer.echo("Restored to a NEW database. Stop services and explicitly select it before resuming.")


deals_app = typer.Typer(help="Explicit operator-supplied commercial data and provider links")
app.add_typer(deals_app, name="deals")


@deals_app.command("terms")
def set_commercial_terms(deal_id: str, file: Path = typer.Option(..., exists=True)) -> None:
    from .agents.deal_desk import IODraft
    from .skills.io_validation import validate_io
    draft = IODraft.model_validate(json.loads(file.read_text(encoding="utf-8")))
    if errors := validate_io(draft.as_io_data()):
        raise typer.BadParameter("; ".join(errors))
    store = SQLiteStore(Settings().database_url)
    try:
        deal = store.get_deal(deal_id)
        if not deal or deal.stage in {"proposal", "contracting", "closed_won", "closed_lost"}:
            raise typer.BadParameter("Terms can only be set on an existing deal before proposal; they never alter an approved contract")
        with store.transaction():
            deal.fields["commercial_terms"] = draft.model_dump()
            store.save_deal(deal)
            store.audit("human:cli", "commercial_terms_supplied", "Explicit terms supplied for subsequent contract review", deal.id)
    finally:
        store.connection.close()


@deals_app.command("link-transcript")
def link_transcript(deal_id: str, transcript_id: str) -> None:
    store = SQLiteStore(Settings().database_url)
    try:
        deal = store.get_deal(deal_id)
        if not deal:
            raise typer.BadParameter("Unknown deal")
        with store.transaction():
            deal.fields["fireflies_transcript_id"] = transcript_id
            store.save_deal(deal)
            store.audit("human:cli", "transcript_linked", transcript_id, deal.id)
    finally:
        store.connection.close()


@app.command("import-contact")
def import_contact(contact_id: str) -> None:
    """Queue a real HubSpot contact fetch; no company scraping or sending."""
    if not contact_id.isdigit():
        raise typer.BadParameter("Use the numeric HubSpot contact ID")
    store = SQLiteStore(Settings().database_url)
    try:
        accepted = store.add_event_once(f"hubspot:import:{contact_id}", "provider.hubspot.contact", {"contact_id": contact_id})
        typer.echo("Contact queued" if accepted else "Contact import already queued")
    finally:
        store.connection.close()


if __name__ == "__main__":
    app()

