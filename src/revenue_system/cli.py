"""Command-line entry point; workflow commands will be added in the next slice."""

import typer
import asyncio
from .orchestration.demo_flow import run_demo
from .container import build_container
from .governance.approvals import ApprovalService

app = typer.Typer(help="Agentic Revenue System CLI")


@app.command()
def demo(mode: str = typer.Option("replay", help="live, record, replay, or test")) -> None:
    """Run the end-to-end demonstration."""
    for line in asyncio.run(run_demo(mode)):
        typer.echo(line)


@app.command("validate-packs")
def validate_packs() -> None:
    """Validate all configured segment packs."""
    typer.echo("Pack validation scaffolded")


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
    event = ApprovalService(build_container().store).decide(approval_id, True)
    typer.echo(f"approved: {event.payload['approval_id']}; action queued in outbox")


@approvals_app.command("reject")
def reject(approval_id: str) -> None:
    event = ApprovalService(build_container().store).decide(approval_id, False)
    typer.echo(f"rejected: {event.payload['approval_id']}")


if __name__ == "__main__":
    app()

