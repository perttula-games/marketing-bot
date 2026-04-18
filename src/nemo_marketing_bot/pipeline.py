"""High-level pipeline: brief -> Nemotron -> publishers."""

from __future__ import annotations

import logging

from .generator import ContentGenerator
from .models import Brief, PostBundle, Platform
from .publishers import get_publisher

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


def run_once(brief: Brief, platforms: list[Platform] | None = None) -> dict[str, str]:
    bundle = generate_bundle(brief, platforms)
    return publish_bundle(bundle)
