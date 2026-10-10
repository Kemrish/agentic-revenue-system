"""Command-line entry point; workflow commands will be added in the next slice."""

import typer

app = typer.Typer(help="Agentic Revenue System CLI")


@app.command()
def demo(mode: str = typer.Option("replay", help="live, record, replay, or test")) -> None:
    """Run the end-to-end demonstration."""
    typer.echo(f"Demo runner scaffolded; selected mode: {mode}")


@app.command("validate-packs")
def validate_packs() -> None:
    """Validate all configured segment packs."""
    typer.echo("Pack validation scaffolded")


if __name__ == "__main__":
    app()

