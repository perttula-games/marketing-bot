"""Typer CLI entrypoint: `nemo-bot ...`."""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .ingest import brief_from_cli, briefs_from_rss
from .models import Platform
from .pipeline import ALL_PLATFORMS, generate_bundle, publish_bundle, run_once
from .scheduler import run_scheduler

app = typer.Typer(add_completion=False, help="NVIDIA Nemotron marketing bot for LinkedIn, X and Instagram.")
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)


def _parse_platforms(value: str | None) -> list[Platform]:
    if not value:
        return ALL_PLATFORMS
    wanted = [p.strip().lower() for p in value.split(",") if p.strip()]
    for p in wanted:
        if p not in ALL_PLATFORMS:
            raise typer.BadParameter(f"Unknown platform '{p}'. Choose from {ALL_PLATFORMS}.")
    return wanted  # type: ignore[return-value]


def _print_bundle(bundle) -> None:  # type: ignore[no-untyped-def]
    for post in bundle.posts:
        table = Table(title=f"[bold]{post.platform.upper()}[/bold] ({len(post.render())} chars)", show_header=False)
        table.add_row(post.render())
        console.print(table)
        if post.image_prompt:
            console.print(f"[dim]Image prompt:[/dim] {post.image_prompt}\n")


@app.command()
def generate(
    topic: str = typer.Option(..., "--topic", "-t", help="Campaign topic / headline."),
    details: str = typer.Option("", "--details", "-d", help="Extra context for the model."),
    url: str | None = typer.Option(None, "--url", help="Link to include in posts."),
    cta: str | None = typer.Option(None, "--cta", help="Preferred call-to-action."),
    tags: str = typer.Option("", "--tags", help="Comma-separated hashtag themes."),
    platforms: str | None = typer.Option(None, "--platforms", "-p", help="Subset, e.g. 'linkedin,x'."),
) -> None:
    """Generate posts from a CLI brief without publishing."""
    brief = brief_from_cli(
        topic=topic,
        details=details,
        url=url,
        cta=cta,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
    )
    bundle = generate_bundle(brief, _parse_platforms(platforms))
    _print_bundle(bundle)


@app.command()
def post(
    topic: str = typer.Option(..., "--topic", "-t"),
    details: str = typer.Option("", "--details", "-d"),
    url: str | None = typer.Option(None, "--url"),
    cta: str | None = typer.Option(None, "--cta"),
    tags: str = typer.Option("", "--tags"),
    platforms: str | None = typer.Option(None, "--platforms", "-p"),
) -> None:
    """Generate AND publish (respects DRY_RUN env var)."""
    brief = brief_from_cli(
        topic=topic,
        details=details,
        url=url,
        cta=cta,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
    )
    results = run_once(brief, _parse_platforms(platforms))
    console.print(results)


@app.command()
def from_rss(
    feed: str = typer.Option(..., "--feed", "-f", help="RSS/Atom URL."),
    limit: int = typer.Option(1, "--limit", "-n", help="Max entries to process."),
    platforms: str | None = typer.Option(None, "--platforms", "-p"),
    publish: bool = typer.Option(False, "--publish", help="Publish after generating."),
) -> None:
    """Generate (and optionally publish) posts from the newest RSS entries."""
    briefs = briefs_from_rss(feed, limit=limit)
    if not briefs:
        console.print("[yellow]No entries found.[/yellow]")
        raise typer.Exit(code=0)
    wanted = _parse_platforms(platforms)
    for brief in briefs:
        console.rule(f"[bold]{brief.topic}[/bold]")
        bundle = generate_bundle(brief, wanted)
        _print_bundle(bundle)
        if publish:
            console.print(publish_bundle(bundle))


@app.command()
def schedule(
    config: Path = typer.Option(Path("schedule.yaml"), "--config", "-c", exists=True, readable=True),
) -> None:
    """Run the blocking scheduler defined by a YAML config."""
    run_scheduler(config)


if __name__ == "__main__":
    app()
