"""Typer CLI entrypoint: `nemo-bot ...`."""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .ingest import brief_from_cli, briefs_from_rss
from .models import Platform
from .pipeline import (
    ALL_PLATFORMS,
    enqueue_bundle,
    generate_bundle,
    publish_bundle,
    publish_draft,
    run_once,
)
from .review import ReviewStore, Status
from .scheduler import run_scheduler

app = typer.Typer(add_completion=False, help="NVIDIA Nemotron marketing bot for LinkedIn, X and Instagram.")
review_app = typer.Typer(help="Review, edit, approve and publish queued drafts.")
app.add_typer(review_app, name="review")
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


# ---------------------------------------------------------------------------
# Review queue commands: `nemo-bot review ...`
# ---------------------------------------------------------------------------


@review_app.command("queue")
def review_queue(
    topic: str = typer.Option(..., "--topic", "-t"),
    details: str = typer.Option("", "--details", "-d"),
    url: str | None = typer.Option(None, "--url"),
    cta: str | None = typer.Option(None, "--cta"),
    tags: str = typer.Option("", "--tags"),
    platforms: str | None = typer.Option(None, "--platforms", "-p"),
) -> None:
    """Generate posts and put them in the review queue (no publish)."""
    brief = brief_from_cli(
        topic=topic,
        details=details,
        url=url,
        cta=cta,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
    )
    bundle = generate_bundle(brief, _parse_platforms(platforms))
    ids = enqueue_bundle(bundle)
    console.print(f"[green]Queued {len(ids)} drafts:[/green] {', '.join(ids)}")
    console.print("Review with: [bold]nemo-bot review list[/bold]")


@review_app.command("list")
def review_list(
    status: str | None = typer.Option(None, "--status", "-s", help="pending|approved|rejected|published|publish_failed"),
    limit: int = typer.Option(20, "--limit", "-n"),
) -> None:
    """List drafts in the queue."""
    drafts = ReviewStore().list(status=status, limit=limit)  # type: ignore[arg-type]
    if not drafts:
        console.print("[dim]No drafts.[/dim]")
        return
    table = Table(show_lines=False)
    table.add_column("id", style="cyan")
    table.add_column("status")
    table.add_column("platform")
    table.add_column("topic")
    table.add_column("updated")
    for d in drafts:
        color = {"pending": "yellow", "approved": "green", "published": "blue",
                 "rejected": "red", "publish_failed": "red"}.get(d.status, "white")
        table.add_row(
            d.id,
            f"[{color}]{d.status}[/{color}]",
            d.platform,
            d.brief.topic[:50],
            d.updated_at.strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)


@review_app.command("show")
def review_show(draft_id: str = typer.Argument(...)) -> None:
    """Show full draft text, hashtags, image prompt, and edit history."""
    store = ReviewStore()
    d = store.get(draft_id)
    console.rule(f"[bold]{d.platform.upper()}[/bold] · {d.status} · {d.id}")
    console.print(f"[dim]Topic:[/dim] {d.brief.topic}")
    if d.brief.url:
        console.print(f"[dim]Source:[/dim] {d.brief.url}")
    console.print()
    console.print(d.to_post().render())
    if d.image_prompt:
        console.print(f"\n[dim]Image:[/dim] {d.image_prompt}")
    if d.publish_id:
        console.print(f"\n[green]Published as:[/green] {d.publish_id}")
    if d.publish_error:
        console.print(f"\n[red]Publish error:[/red] {d.publish_error}")
    history = store.edit_history(draft_id)
    if history:
        console.print("\n[bold]Edit history[/bold]")
        for h in history:
            console.print(f"  {h['edited_at']}  {h['field']}: {h['old_value']!r} → {h['new_value']!r}")


@review_app.command("edit")
def review_edit(
    draft_id: str = typer.Argument(...),
    text: str | None = typer.Option(None, "--text", help="Replace the post body."),
    hashtags: str | None = typer.Option(None, "--hashtags", help="Comma-separated replacement hashtags."),
    image_prompt: str | None = typer.Option(None, "--image-prompt", help="New image prompt / URL (Instagram)."),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Open $EDITOR to edit the body."),
) -> None:
    """Edit a pending draft. Use --interactive to open your editor."""
    store = ReviewStore()
    current = store.get(draft_id)
    new_text = text
    if interactive:
        new_text = typer.edit(current.text) or current.text
    new_tags = [t.strip() for t in hashtags.split(",") if t.strip()] if hashtags is not None else None
    updated = store.edit(
        draft_id,
        text=new_text,
        hashtags=new_tags,
        image_prompt=image_prompt,
    )
    console.print(f"[green]Updated {draft_id}[/green]")
    console.print(updated.to_post().render())


@review_app.command("approve")
def review_approve(
    draft_id: str = typer.Argument(...),
    and_publish: bool = typer.Option(False, "--publish", help="Publish immediately after approving."),
) -> None:
    """Mark a draft approved. Optionally publish right after."""
    store = ReviewStore()
    d = store.approve(draft_id)
    console.print(f"[green]Approved[/green] {d.id} ({d.platform})")
    if and_publish:
        d = publish_draft(draft_id, store)
        if d.status == "published":
            console.print(f"[blue]Published:[/blue] {d.publish_id}")
        else:
            console.print(f"[red]Publish failed:[/red] {d.publish_error}")


@review_app.command("reject")
def review_reject(draft_id: str = typer.Argument(...)) -> None:
    """Reject a draft so it won't be published."""
    d = ReviewStore().reject(draft_id)
    console.print(f"[red]Rejected[/red] {d.id}")


@review_app.command("reopen")
def review_reopen(draft_id: str = typer.Argument(...)) -> None:
    """Move a rejected / approved / publish_failed draft back to pending so you can edit it."""
    d = ReviewStore().reopen(draft_id)
    console.print(f"[yellow]Reopened[/yellow] {d.id} (now pending)")


@review_app.command("publish")
def review_publish(draft_id: str = typer.Argument(...)) -> None:
    """Publish a previously approved draft."""
    d = publish_draft(draft_id)
    if d.status == "published":
        console.print(f"[blue]Published[/blue] {d.id}: {d.publish_id}")
    else:
        console.print(f"[red]Publish failed:[/red] {d.publish_error}")
        raise typer.Exit(code=1)


@app.command("telegram-approve")
def telegram_approve() -> None:
    """Run the Telegram approval bot.

    Approvers get a message per pending draft with inline buttons for
    approve/reject/publish, quick-edit, and free-form AI-assisted revision.
    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_APPROVER_CHAT_IDS in .env.
    """
    from .telegram_bot import run_telegram_bot

    run_telegram_bot()


if __name__ == "__main__":
    app()
