"""Command-line entry point; workflow commands will be added in the next slice."""

import typer
import asyncio
from .orchestration.demo_flow import run_demo

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


if __name__ == "__main__":
    app()

