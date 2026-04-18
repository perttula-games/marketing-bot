"""Platform publishers for LinkedIn, X, and Instagram.

Each publisher implements `publish(post)` and raises on failure. They honour
`settings.dry_run` — when true, no network calls are made and the rendered post
is simply logged. This keeps the main flow safe to run end-to-end without live
API credentials.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

import httpx
import tweepy

from .config import settings
from .models import GeneratedPost

logger = logging.getLogger(__name__)

X_MAX_CHARS = 280


class Publisher(Protocol):
    platform: str

    def publish(self, post: GeneratedPost) -> str: ...


class LinkedInPublisher:
    """Posts plain text to a personal LinkedIn profile via the UGC Posts API."""

    platform = "linkedin"
    _endpoint = "https://api.linkedin.com/v2/ugcPosts"

    def publish(self, post: GeneratedPost) -> str:
        body = post.render()
        if settings.dry_run:
            logger.info("[DRY RUN] LinkedIn post (%d chars):\n%s", len(body), body)
            return "dry-run"
        if not settings.linkedin_access_token or not settings.linkedin_author_urn:
            raise RuntimeError("LinkedIn credentials missing. See .env.example.")

        payload = {
            "author": settings.linkedin_author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": body},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        headers = {
            "Authorization": f"Bearer {settings.linkedin_access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(self._endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            post_id = resp.headers.get("x-restli-id", "unknown")
            logger.info("LinkedIn post published: %s", post_id)
            return post_id


class XPublisher:
    """Posts a tweet via X API v2 (tweepy.Client, OAuth 1.0a user context)."""

    platform = "x"

    def publish(self, post: GeneratedPost) -> str:
        body = post.render()
        if len(body) > X_MAX_CHARS:
            body = body[: X_MAX_CHARS - 1].rstrip() + "\u2026"
        if settings.dry_run:
            logger.info("[DRY RUN] X tweet (%d chars):\n%s", len(body), body)
            return "dry-run"
        if not all(
            [
                settings.x_api_key,
                settings.x_api_secret,
                settings.x_access_token,
                settings.x_access_token_secret,
            ]
        ):
            raise RuntimeError("X credentials missing. See .env.example.")
        client = tweepy.Client(
            consumer_key=settings.x_api_key,
            consumer_secret=settings.x_api_secret,
            access_token=settings.x_access_token,
            access_token_secret=settings.x_access_token_secret,
        )
        response = client.create_tweet(text=body)
        tweet_id = str(response.data["id"])
        logger.info("X tweet published: %s", tweet_id)
        return tweet_id


class InstagramPublisher:
    """Publishes an Instagram feed post via the Graph API.

    Instagram requires a publicly reachable image URL. For text-only briefs you
    must supply one via `post.image_prompt` (we treat it as a URL when it looks
    like one) or pre-render an image elsewhere and inject the URL. In DRY_RUN
    mode we just log the intent.
    """

    platform = "instagram"
    _graph = "https://graph.facebook.com/v21.0"

    def publish(self, post: GeneratedPost) -> str:
        body = post.render()
        image_url = post.image_prompt if (post.image_prompt or "").startswith("http") else None

        if settings.dry_run:
            logger.info(
                "[DRY RUN] Instagram caption (%d chars), image_url=%s:\n%s",
                len(body),
                image_url,
                body,
            )
            return "dry-run"
        if not settings.ig_access_token or not settings.ig_user_id:
            raise RuntimeError("Instagram credentials missing. See .env.example.")
        if not image_url:
            raise RuntimeError(
                "Instagram feed posts require a public image URL. "
                "Set post.image_prompt to a URL or extend the pipeline with an image generator."
            )

        with httpx.Client(timeout=60) as client:
            create = client.post(
                f"{self._graph}/{settings.ig_user_id}/media",
                data={
                    "image_url": image_url,
                    "caption": body,
                    "access_token": settings.ig_access_token,
                },
            )
            create.raise_for_status()
            container_id = create.json()["id"]

            # The container needs a moment to finish processing before publish.
            time.sleep(3)

            publish = client.post(
                f"{self._graph}/{settings.ig_user_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": settings.ig_access_token,
                },
            )
            publish.raise_for_status()
            media_id = publish.json()["id"]
            logger.info("Instagram post published: %s", media_id)
            return media_id


_REGISTRY: dict[str, type[Publisher]] = {
    "linkedin": LinkedInPublisher,
    "x": XPublisher,
    "instagram": InstagramPublisher,
}


def get_publisher(platform: str) -> Publisher:
    try:
        return _REGISTRY[platform]()
    except KeyError as err:
        raise ValueError(f"Unknown platform: {platform}") from err
