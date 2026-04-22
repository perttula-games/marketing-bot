"""High-level pipeline: brief -> Nemotron -> publishers."""

from __future__ import annotations

import logging

from .generator import ContentGenerator
from .models import Brief, PostBundle, Platform
from .publishers import get_publisher
from .review import DraftRecord, ReviewStore

logger = logging.getLogger(__name__)

ALL_PLATFORMS: list[Platform] = ["linkedin", "x", "instagram"]


def generate_bundle(brief: Brief, platforms: list[Platform] | None = None) -> PostBundle:
    return ContentGenerator().generate(brief, platforms or ALL_PLATFORMS)


def publish_bundle(bundle: PostBundle) -> dict[str, str]:
    """Publish every post in the bundle. Failures are logged but don't stop siblings."""
    results: dict[str, str] = {}
    for post in bundle.posts:
        publisher = get_publisher(post.platform)
        try:
            results[post.platform] = publisher.publish(post)
        except Exception as err:  # noqa: BLE001 — we intentionally continue other platforms
            logger.exception("Publishing to %s failed: %s", post.platform, err)
            results[post.platform] = f"error: {err}"
    return results


def enqueue_bundle(bundle: PostBundle, store: ReviewStore | None = None) -> list[str]:
    """Queue a generated bundle for human review. Returns draft ids."""
    return (store or ReviewStore()).enqueue_bundle(bundle)


def publish_draft(draft_id: str, store: ReviewStore | None = None) -> DraftRecord:
    """Publish a single approved draft. Marks the row published/publish_failed."""
    store = store or ReviewStore()
    draft = store.get(draft_id)
    if draft.status != "approved":
        raise ValueError(f"Draft {draft_id} is {draft.status}; only approved drafts can be published.")
    publisher = get_publisher(draft.platform)
    try:
        publish_id = publisher.publish(draft.to_post())
    except Exception as err:  # noqa: BLE001
        logger.exception("Publishing draft %s to %s failed: %s", draft_id, draft.platform, err)
        store.set_status(draft_id, "publish_failed", publish_error=str(err))
        return store.get(draft_id)
    store.set_status(draft_id, "published", publish_id=publish_id)
    return store.get(draft_id)


def run_once(
    brief: Brief,
    platforms: list[Platform] | None = None,
    *,
    auto_publish: bool = False,
) -> dict[str, str] | list[str]:
    """Generate, then either publish immediately or queue for review.

    Returns the publish results dict when auto_publish=True, or the list of
    enqueued draft ids when auto_publish=False (the default — safer).
    """
    bundle = generate_bundle(brief, platforms)
    if auto_publish:
        return publish_bundle(bundle)
    return enqueue_bundle(bundle)
