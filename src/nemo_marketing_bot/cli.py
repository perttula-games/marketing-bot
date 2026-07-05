"""Typer CLI entrypoint: `nemo-bot ...`."""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .creator_outreach import build_creator_plan, creator_plan_to_csv, parse_creator_channels
from .ingest import brief_from_cli, briefs_from_rss
from .models import Platform, PublishPlatform
from .pipeline import (
    ALL_PLATFORMS,
    CONTENT_PLATFORMS,
    PUBLISH_PLATFORMS,
    enqueue_bundle,
    generate_bundle,
    publish_bundle,
    publish_draft,
    run_once,
)
from .review import ReviewStore, Status
from .strategy import (
    build_generation_system_prompt,
    load_editable_strategy_prompt,
    marketing_system_prompt_path,
    write_default_strategy_prompt,
)

app = typer.Typer(add_completion=False, help="NVIDIA Nemotron marketing bot for game marketing channels.")
review_app = typer.Typer(help="Review, edit, approve and publish queued drafts.")
creator_app = typer.Typer(help="Plan creator outreach and manual channel setup.")
strategy_app = typer.Typer(help="Manage the editable marketing system prompt.")
app.add_typer(review_app, name="review")
app.add_typer(creator_app, name="creators")
app.add_typer(strategy_app, name="strategy")
console = Console()

SENSITIVE_OUTPUT_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        "authorized_keys",
        "id_rsa",
        "id_rsa.pub",
        "id_ed25519",
        "id_ed25519.pub",
        "known_hosts",
    }
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
# Silence httpx INFO-level "HTTP Request: POST https://.../botTOKEN/..." lines
# that would otherwise leak the Telegram bot token into stdout / log files.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def _parse_platforms(
    value: str | None,
    *,
    default: list[Platform] | None = None,
    publish_only: bool = False,
) -> list[Platform]:
    choices: list[Platform] = list(PUBLISH_PLATFORMS if publish_only else CONTENT_PLATFORMS)
    if not value:
        return list(default or choices)
    wanted = [p.strip().lower() for p in value.split(",") if p.strip()]
    if any(p in {"all", "all-content", "content"} for p in wanted):
        if publish_only:
            raise typer.BadParameter(f"Publishing supports only: {PUBLISH_PLATFORMS}.")
        return list(CONTENT_PLATFORMS)
    if any(p in {"publish", "all-publish", "publishers"} for p in wanted):
        return list(PUBLISH_PLATFORMS)
    for p in wanted:
        if p not in choices:
            raise typer.BadParameter(f"Unknown platform '{p}'. Choose from {choices}.")
    return wanted  # type: ignore[return-value]


def _parse_publish_platforms(value: str | None) -> list[PublishPlatform]:
    platforms = _parse_platforms(value, default=list(PUBLISH_PLATFORMS), publish_only=True)
    return platforms  # type: ignore[return-value]


def _reject_sensitive_output_path(path: Path) -> None:
    parts = {part.lower() for part in path.expanduser().parts}
    if path.name.lower() in SENSITIVE_OUTPUT_NAMES or ".ssh" in parts:
        raise typer.BadParameter(f"Refusing to write to sensitive path: {path}")


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
    platforms: str | None = typer.Option(None, "--platforms", "-p", help="Subset, e.g. 'linkedin,tiktok,youtube' or 'all-content'."),
) -> None:
    """Generate posts from a CLI brief without publishing."""
    brief = brief_from_cli(
        topic=topic,
        details=details,
        url=url,
        cta=cta,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
    )
    bundle = generate_bundle(brief, _parse_platforms(platforms, default=list(ALL_PLATFORMS)))
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
    results = run_once(brief, _parse_publish_platforms(platforms))
    console.print(results)


@app.command()
def publish(
    platform: str = typer.Option(..., "--platform", help="Target platform (e.g. bluesky, linkedin, discord)."),
    text: str | None = typer.Option(None, "--text", help="Exact post text to publish. Use --from-file to read from disk instead."),
    from_file: Path | None = typer.Option(None, "--from-file", help="Read post text from this file (UTF-8)."),
    hashtags: str = typer.Option("", "--hashtags", help="Comma-separated hashtags appended on a new line."),
    image_prompt: str | None = typer.Option(None, "--image-prompt", help="Public image URL (required for Instagram, optional preview hint elsewhere)."),
) -> None:
    """Publish a pre-written post verbatim through the proper Publisher.

    Use this instead of raw HTTP calls when the user has supplied exact copy
    they want posted as-is. The proper Publisher class handles platform
    quirks like Bluesky link-preview embeds via uploadBlob.
    """
    from .publishers import get_publisher
    from .models import GeneratedPost

    if platform not in set(PUBLISH_PLATFORMS):
        raise typer.BadParameter(
            f"--platform must be one of: {', '.join(sorted(PUBLISH_PLATFORMS))}"
        )
    if (text is None) == (from_file is None):
        raise typer.BadParameter("Provide exactly one of --text or --from-file.")

    if from_file is not None:
        body = from_file.read_text(encoding="utf-8").strip()
    else:
        assert text is not None
        body = text

    if not body:
        raise typer.BadParameter("Post text is empty.")

    tag_list = [t.strip().lstrip("#") for t in hashtags.split(",") if t.strip()]
    post_obj = GeneratedPost(
        platform=platform,  # type: ignore[arg-type]
        text=body,
        hashtags=tag_list,
        image_prompt=image_prompt,
    )
    publisher = get_publisher(platform)
    result = publisher.publish(post_obj)
    console.print({platform: result})


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
    wanted = _parse_publish_platforms(platforms) if publish else _parse_platforms(platforms, default=list(ALL_PLATFORMS))
    for brief in briefs:
        console.rule(f"[bold]{brief.topic}[/bold]")
        bundle = generate_bundle(brief, wanted)
        _print_bundle(bundle)
        if publish:
            console.print(publish_bundle(bundle))


@app.command()
def devlog(
    site: str = typer.Option(
        "https://perttulagamestudio.com",
        "--site",
        "-s",
        help="Website origin that publishes /devlog.json.",
    ),
    platforms: str | None = typer.Option(
        None, "--platforms", "-p", help="Subset, e.g. 'linkedin,bluesky,discord' or 'all-content'."
    ),
    limit: int | None = typer.Option(
        None, "--limit", "-n", help="Cap on devlog posts to process this run."
    ),
    all_posts: bool = typer.Option(
        False, "--all", help="Process every post in the index, ignoring the seen-state file."
    ),
    publish: bool = typer.Option(
        False, "--publish", help="Publish immediately. Without this, drafts go to the review queue."
    ),
    dry_state: bool = typer.Option(
        False,
        "--dry-state",
        help="Do not update the seen-state file (useful for dry runs).",
    ),
) -> None:
    """Generate marketing posts from the newest devlog entries on a Perttula site.

    Reads ``<site>/devlog.json`` (built by the website's devlog-prerender
    plugin), filters out slugs already processed, and either enqueues the
    bundle for review or publishes immediately.
    """
    from .devlog import (
        brief_from_devlog,
        ensure_post_has_url,
        fetch_devlog_index,
        filter_published,
        filter_unseen,
        mark_seen,
        strip_discord_self_promo,
    )

    items = fetch_devlog_index(site)
    if not items:
        console.print("[yellow]No devlog entries found.[/yellow]")
        raise typer.Exit(code=0)

    items = filter_published(items)
    if not items:
        console.print("[yellow]No devlog posts have reached their publish date yet.[/yellow]")
        raise typer.Exit(code=0)

    candidates = items if all_posts else filter_unseen(items)
    if not candidates:
        console.print("[green]No new devlog posts since last run.[/green]")
        raise typer.Exit(code=0)

    if limit is not None and limit > 0:
        candidates = candidates[:limit]

    wanted = (
        _parse_publish_platforms(platforms)
        if publish
        else _parse_platforms(platforms, default=list(ALL_PLATFORMS))
    )

    processed_slugs: list[str] = []
    for item in candidates:
        console.rule(f"[bold]{item.title}[/bold] ([dim]{item.slug}[/dim])")
        brief = brief_from_devlog(item)
        bundle = generate_bundle(brief, wanted)
        for post in bundle.posts:
            strip_discord_self_promo(post)
            ensure_post_has_url(post, item.url)
        _print_bundle(bundle)
        if publish:
            console.print(publish_bundle(bundle))
        else:
            ids = enqueue_bundle(bundle)
            console.print(
                f"[green]Queued {len(ids)} drafts:[/green] {', '.join(ids)}"
            )
        processed_slugs.append(item.slug)

    if processed_slugs and not dry_state:
        mark_seen(processed_slugs)
        console.print(
            f"[dim]Marked {len(processed_slugs)} slug(s) as seen.[/dim]"
        )


# ---------------------------------------------------------------------------
# Editable marketing strategy prompt: `nemo-bot strategy ...`
# ---------------------------------------------------------------------------


@strategy_app.command("path")
def strategy_path() -> None:
    """Print the active editable marketing system prompt path."""
    console.print(marketing_system_prompt_path())


@strategy_app.command("show")
def strategy_show(
    compiled: bool = typer.Option(False, "--compiled", help="Show the full prompt including non-negotiable runtime rules."),
) -> None:
    """Print the active marketing strategy prompt."""
    console.print(build_generation_system_prompt() if compiled else load_editable_strategy_prompt())


@strategy_app.command("init")
def strategy_init(
    path: Path | None = typer.Option(None, "--path", help="Prompt file path. Defaults to MARKETING_SYSTEM_PROMPT_FILE."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite an existing prompt file."),
) -> None:
    """Create a starter editable marketing system prompt file."""
    if path is not None:
        _reject_sensitive_output_path(path)
    target, wrote = write_default_strategy_prompt(path, force=force)
    if wrote:
        console.print(f"[green]Wrote marketing system prompt:[/green] {target}")
    else:
        console.print(f"[yellow]Prompt already exists:[/yellow] {target}")


# ---------------------------------------------------------------------------
# Creator outreach and manual page setup: `nemo-bot creators ...`
# ---------------------------------------------------------------------------


def _print_creator_plan(plan) -> None:  # type: ignore[no-untyped-def]
    console.rule(f"[bold]Manual channel setup for {plan.game_name}[/bold]")
    setup_table = Table(show_lines=True)
    setup_table.add_column("Prio", style="cyan", width=5)
    setup_table.add_column("Channel", style="bold")
    setup_table.add_column("Page / asset")
    setup_table.add_column("First checklist")
    setup_table.add_column("Done when")
    for task in plan.setup_tasks:
        setup_table.add_row(
            str(task.priority),
            task.channel,
            task.title,
            "\n".join(task.checklist),
            task.done_when,
        )
    console.print(setup_table)

    console.rule("[bold]Creator target matrix[/bold]")
    target_table = Table(show_lines=True)
    target_table.add_column("Prio", style="cyan", width=5)
    target_table.add_column("Channel", style="bold")
    target_table.add_column("Who to find")
    target_table.add_column("Search")
    target_table.add_column("Deliverables")
    target_table.add_column("Metrics")
    for target in plan.creator_targets:
        target_table.add_row(
            str(target.priority),
            target.channel,
            target.target_profile,
            "\n".join(target.search_queries[:3]),
            "\n".join(target.deliverables),
            "\n".join(target.metrics[:4]),
        )
    console.print(target_table)


def _print_outreach_templates(plan) -> None:  # type: ignore[no-untyped-def]
    console.rule("[bold]Outreach templates[/bold]")
    for name, template in plan.outreach_templates.items():
        table = Table(title=name, show_header=False)
        table.add_row(template)
        console.print(table)


@creator_app.command("plan")
def creators_plan(
    game_name: str = typer.Option("NemoClaw", "--game", help="Game / project name."),
    genre: str = typer.Option("PC indie/AA game", "--genre", help="Short genre or positioning."),
    audience: str = typer.Option("PC and console players", "--audience", help="Primary audience."),
    budget: str = typer.Option("organic-first / low paid test", "--budget", help="Budget posture for outreach."),
    language: str = typer.Option("fi,en", "--language", help="Creator language targets."),
    store_url: str | None = typer.Option(None, "--store-url", help="Steam/store URL if available."),
    discord_url: str | None = typer.Option(None, "--discord-url", help="Discord invite if available."),
    channels: str | None = typer.Option(None, "--channels", "-c", help="Comma-separated creator channels or 'all'."),
    templates: bool = typer.Option(True, "--templates/--no-templates", help="Show outreach templates."),
) -> None:
    """Print the manual page setup list and creator target matrix."""
    try:
        wanted = parse_creator_channels(channels)
    except ValueError as err:
        raise typer.BadParameter(str(err)) from err
    plan = build_creator_plan(
        game_name=game_name,
        genre=genre,
        audience=audience,
        budget=budget,
        language=language,
        store_url=store_url,
        discord_url=discord_url,
        channels=wanted,
    )
    _print_creator_plan(plan)
    if templates:
        _print_outreach_templates(plan)


@creator_app.command("export")
def creators_export(
    output: Path = typer.Option(Path("creator-outreach.csv"), "--output", "-o", help="CSV file to write."),
    game_name: str = typer.Option("NemoClaw", "--game", help="Game / project name."),
    genre: str = typer.Option("PC indie/AA game", "--genre", help="Short genre or positioning."),
    audience: str = typer.Option("PC and console players", "--audience", help="Primary audience."),
    budget: str = typer.Option("organic-first / low paid test", "--budget", help="Budget posture for outreach."),
    language: str = typer.Option("fi,en", "--language", help="Creator language targets."),
    store_url: str | None = typer.Option(None, "--store-url", help="Steam/store URL if available."),
    discord_url: str | None = typer.Option(None, "--discord-url", help="Discord invite if available."),
    channels: str | None = typer.Option(None, "--channels", "-c", help="Comma-separated creator channels or 'all'."),
) -> None:
    """Export the creator target matrix to CSV for manual outreach tracking."""
    _reject_sensitive_output_path(output)
    try:
        wanted = parse_creator_channels(channels)
    except ValueError as err:
        raise typer.BadParameter(str(err)) from err
    plan = build_creator_plan(
        game_name=game_name,
        genre=genre,
        audience=audience,
        budget=budget,
        language=language,
        store_url=store_url,
        discord_url=discord_url,
        channels=wanted,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(creator_plan_to_csv(plan), encoding="utf-8")
    console.print(f"[green]Wrote creator outreach CSV:[/green] {output}")


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
    bundle = generate_bundle(brief, _parse_platforms(platforms, default=list(ALL_PLATFORMS)))
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
