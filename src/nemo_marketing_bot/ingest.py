"""Turn CLI briefs and RSS feed entries into `Brief` objects."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import feedparser
import httpx

from .models import Brief
from .security import assert_safe_url, sanitize_untrusted_text

logger = logging.getLogger(__name__)

# Cap on raw feed bytes we will parse, to avoid memory-exhaustion DoS from a
# malicious or buggy feed. 5 MiB is plenty for any real RSS/Atom payload.
MAX_FEED_BYTES = 5 * 1024 * 1024


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
    """Fetch an RSS/Atom feed and return the newest entries as briefs.

    The URL is validated against SSRF (no file://, no private/loopback IPs).
    Entry text is sanitised before being embedded in any LLM prompt.
    """
    assert_safe_url(feed_url, label="feed_url")
    logger.info("Fetching RSS feed %s", feed_url)

    # Fetch with httpx so we control timeout, redirect policy, and size cap.
    # Allow redirects but re-validate every hop's destination.
    with httpx.Client(timeout=15.0, follow_redirects=False) as client:
        body = _fetch_with_safe_redirects(client, feed_url, hops_left=3)

    parsed = feedparser.parse(body)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"Failed to parse feed {feed_url}: {parsed.bozo_exception}")

    briefs: list[Brief] = []
    for entry in parsed.entries[:limit]:
        published = _entry_datetime(entry)
        if since is not None and published is not None and published < since:
            continue
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
        link = getattr(entry, "link", None)
        # If the entry has a link, validate it before we ever pass it to the
        # generator (which would put it in a prompt and possibly a published post).
        if link:
            try:
                assert_safe_url(link, label="entry.link")
            except Exception as err:  # noqa: BLE001
                logger.warning("Dropping unsafe entry link %s: %s", link, err)
                link = None
        briefs.append(
            Brief(
                topic=sanitize_untrusted_text(getattr(entry, "title", "Untitled"), max_chars=300),
                details=sanitize_untrusted_text(_strip_html(summary), max_chars=1200),
                url=link,
                tags=[t.term for t in getattr(entry, "tags", []) if hasattr(t, "term")],
            )
        )
    return briefs


def _fetch_with_safe_redirects(client: httpx.Client, url: str, *, hops_left: int) -> bytes:
    """Manually follow redirects, re-validating every Location header."""
    current = url
    while True:
        with client.stream("GET", current, headers={"User-Agent": "nemo-marketing-bot/0.1"}) as resp:
            if resp.status_code in (301, 302, 303, 307, 308):
                if hops_left <= 0:
                    raise RuntimeError(f"Too many redirects fetching {url}")
                location = resp.headers.get("location")
                if not location:
                    raise RuntimeError(f"Redirect from {current} without Location header")
                # Resolve relative redirects against the current URL.
                current = str(httpx.URL(current).join(location))
                assert_safe_url(current, label="redirect")
                hops_left -= 1
                continue
            resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > MAX_FEED_BYTES:
                    raise RuntimeError(f"Feed body exceeds {MAX_FEED_BYTES} bytes")
                chunks.append(chunk)
            return b"".join(chunks)


def _entry_datetime(entry: object) -> datetime | None:
    parsed_time = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed_time:
        return None
    return datetime(*parsed_time[:6], tzinfo=UTC)


def _strip_html(text: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", text).strip()
