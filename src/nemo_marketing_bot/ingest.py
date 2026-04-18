"""Turn CLI briefs and RSS feed entries into `Brief` objects."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import feedparser

from .models import Brief

logger = logging.getLogger(__name__)


def brief_from_cli(
    topic: str,
    details: str = "",
    url: str | None = None,
    cta: str | None = None,
    tags: list[str] | None = None,
) -> Brief:
    return Brief(
        topic=topic,
        details=details,
        url=url,
        call_to_action=cta,
        tags=tags or [],
    )


def briefs_from_rss(feed_url: str, limit: int = 3, since: datetime | None = None) -> list[Brief]:
    """Fetch an RSS/Atom feed and return the newest entries as briefs."""
    logger.info("Fetching RSS feed %s", feed_url)
    parsed = feedparser.parse(feed_url)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"Failed to parse feed {feed_url}: {parsed.bozo_exception}")

    briefs: list[Brief] = []
    for entry in parsed.entries[:limit]:
        published = _entry_datetime(entry)
        if since is not None and published is not None and published < since:
            continue
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
        briefs.append(
            Brief(
                topic=getattr(entry, "title", "Untitled"),
                details=_strip_html(summary)[:1200],
                url=getattr(entry, "link", None),
                tags=[t.term for t in getattr(entry, "tags", []) if hasattr(t, "term")],
            )
        )
    return briefs


def _entry_datetime(entry: object) -> datetime | None:
    parsed_time = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed_time:
        return None
    return datetime(*parsed_time[:6], tzinfo=UTC)


def _strip_html(text: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", text).strip()
