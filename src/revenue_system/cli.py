"""Command-line entry point; workflow commands will be added in the next slice."""

import typer
import asyncio
from .orchestration.demo_flow import run_demo
from .container import build_container

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


if __name__ == "__main__":
    app()

