"""Discover and ingest devlog posts from a Perttula Game Studio website.

The website build emits ``/devlog.json`` listing every published devlog
post with title, excerpt, image, and a permalink. This module:

1. Fetches that index over HTTPS (with the same SSRF defences as the RSS
   ingester).
2. Tracks which slugs we have already turned into briefs in a small JSON
   state file under ``~/.nemo-bot/devlog-seen.json``.
3. Converts new entries into ``Brief`` objects, sanitising every field
   that originated outside our control.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from .models import Brief
from .security import assert_safe_url, sanitize_untrusted_text

logger = logging.getLogger(__name__)

# Cap the JSON index size so a malicious or buggy host cannot exhaust memory.
MAX_INDEX_BYTES = 1 * 1024 * 1024  # 1 MiB is plenty for hundreds of posts.

DEFAULT_SITE_ORIGIN = "https://perttulagamestudio.com"
DEFAULT_INDEX_PATH = "/devlog.json"

DEFAULT_STATE_FILE = Path("~/.nemo-bot/devlog-seen.json").expanduser()


@dataclass(frozen=True)
class DevlogItem:
    """A single devlog entry as published in /devlog.json."""

    slug: str
    publish_date: str
    title: str
    excerpt: str
    url: str
    image: str | None
    image_alt: str | None
    category: str | None


def fetch_devlog_index(
    site_origin: str = DEFAULT_SITE_ORIGIN,
    *,
    index_path: str = DEFAULT_INDEX_PATH,
) -> list[DevlogItem]:
    """Fetch ``<site_origin><index_path>`` and return the listed posts.

    URL is validated against SSRF, redirects are followed manually with
    re-validation, and the response body is capped at ``MAX_INDEX_BYTES``.
    """
    index_url = site_origin.rstrip("/") + index_path
    assert_safe_url(index_url, label="devlog_index_url")
    logger.info("Fetching devlog index %s", index_url)

    with httpx.Client(timeout=15.0, follow_redirects=False) as client:
        body = _fetch_with_safe_redirects(client, index_url, hops_left=3)

    try:
        payload: Any = json.loads(body)
    except json.JSONDecodeError as err:
        raise RuntimeError(f"Devlog index is not valid JSON: {err}") from err

    if not isinstance(payload, dict) or not isinstance(payload.get("posts"), list):
        raise RuntimeError("Devlog index missing 'posts' array")

    items: list[DevlogItem] = []
    for raw in payload["posts"]:
        if not isinstance(raw, dict):
            continue
        item = _parse_item(raw)
        if item is not None:
            items.append(item)
    return items


def _parse_item(raw: dict[str, Any]) -> DevlogItem | None:
    slug = raw.get("slug")
    title = raw.get("title")
    url = raw.get("url")
    if not isinstance(slug, str) or not isinstance(title, str) or not isinstance(url, str):
        return None
    try:
        assert_safe_url(url, label="devlog.url")
    except Exception as err:  # noqa: BLE001
        logger.warning("Dropping devlog entry %s with unsafe url: %s", slug, err)
        return None

    image = raw.get("image")
    if isinstance(image, str):
        try:
            assert_safe_url(image, label="devlog.image")
        except Exception as err:  # noqa: BLE001
            logger.warning("Dropping unsafe image for %s: %s", slug, err)
            image = None
    else:
        image = None

    return DevlogItem(
        slug=slug,
        publish_date=str(raw.get("publishDate", "")),
        title=title,
        excerpt=str(raw.get("excerpt", "")),
        url=url,
        image=image,
        image_alt=raw.get("imageAlt") if isinstance(raw.get("imageAlt"), str) else None,
        category=raw.get("category") if isinstance(raw.get("category"), str) else None,
    )


def brief_from_devlog(item: DevlogItem) -> Brief:
    """Turn a devlog item into a sanitised Brief for the generator."""
    detail_parts: list[str] = []
    if item.excerpt:
        detail_parts.append(item.excerpt)
    if item.category:
        detail_parts.append(f"Category: {item.category}.")
    if item.image_alt:
        detail_parts.append(f"Hero image shows: {item.image_alt}.")
    detail_parts.append(
        "Source: latest devlog post on perttulagamestudio.com — "
        "drive readers to the full post and (where it fits the channel) "
        "the studio Discord or demo."
    )
    details = " ".join(detail_parts)

    tags: list[str] = []
    if item.category:
        tags.append(item.category)
    tags.append("devlog")

    return Brief(
        topic=sanitize_untrusted_text(item.title, max_chars=300),
        details=sanitize_untrusted_text(details, max_chars=1500),
        url=item.url,
        tags=tags,
    )


# ---------------------------------------------------------------------------
# Seen-slug state file
# ---------------------------------------------------------------------------


def load_seen(state_file: Path = DEFAULT_STATE_FILE) -> dict[str, str]:
    """Return mapping of slug -> ISO timestamp of when it was first processed."""
    if not state_file.exists():
        return {}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        logger.warning("Devlog state file unreadable, starting fresh: %s", err)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def mark_seen(slugs: list[str], state_file: Path = DEFAULT_STATE_FILE) -> None:
    """Add ``slugs`` to the seen state file (idempotent)."""
    if not slugs:
        return
    from datetime import UTC, datetime

    seen = load_seen(state_file)
    now = datetime.now(UTC).isoformat()
    for slug in slugs:
        seen.setdefault(slug, now)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(seen, indent=2, sort_keys=True), encoding="utf-8")


def filter_unseen(
    items: list[DevlogItem],
    state_file: Path = DEFAULT_STATE_FILE,
) -> list[DevlogItem]:
    seen = load_seen(state_file)
    return [item for item in items if item.slug not in seen]


def filter_published(
    items: list[DevlogItem],
    today: date | None = None,
) -> list[DevlogItem]:
    """Drop items whose ``publish_date`` is in the future.

    Items with a missing or unparseable date are kept (treated as already
    published) so manual entries without a date still flow through.
    """
    today = today or date.today()
    kept: list[DevlogItem] = []
    for item in items:
        if not item.publish_date:
            kept.append(item)
            continue
        try:
            published_on = date.fromisoformat(item.publish_date)
        except ValueError:
            logger.warning(
                "Devlog %s has unparseable publishDate %r; treating as published",
                item.slug,
                item.publish_date,
            )
            kept.append(item)
            continue
        if published_on > today:
            logger.info(
                "Skipping devlog %s: publishDate %s is in the future",
                item.slug,
                item.publish_date,
            )
            continue
        kept.append(item)
    return kept


# ---------------------------------------------------------------------------
# Internal HTTP helper (mirrors ingest.py to keep redirect re-validation)
# ---------------------------------------------------------------------------


def _fetch_with_safe_redirects(client: httpx.Client, url: str, *, hops_left: int) -> bytes:
    current = url
    while True:
        with client.stream(
            "GET",
            current,
            headers={"User-Agent": "nemo-marketing-bot/0.1 devlog"},
        ) as resp:
            if resp.status_code in (301, 302, 303, 307, 308):
                if hops_left <= 0:
                    raise RuntimeError(f"Too many redirects fetching {url}")
                location = resp.headers.get("location")
                if not location:
                    raise RuntimeError(f"Redirect from {current} without Location header")
                current = str(httpx.URL(current).join(location))
                assert_safe_url(current, label="devlog_redirect")
                hops_left -= 1
                continue
            resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > MAX_INDEX_BYTES:
                    raise RuntimeError(f"Devlog index exceeds {MAX_INDEX_BYTES} bytes")
                chunks.append(chunk)
            return b"".join(chunks)
