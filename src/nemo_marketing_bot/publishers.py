"""Platform publishers for LinkedIn, X, Instagram, and Bluesky.

Each publisher implements `publish(post)` and raises on failure. They honour
`settings.dry_run` — when true, no network calls are made and the rendered post
is simply logged. This keeps the main flow safe to run end-to-end without live
API credentials.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx
import tweepy

from .config import ig_image_allowlist, settings
from .models import GeneratedPost
from .security import is_allowed_image_host

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
        candidate = post.image_prompt if (post.image_prompt or "").startswith("http") else None
        allowlist = ig_image_allowlist()
        image_url = candidate if (candidate and is_allowed_image_host(candidate, allowlist)) else None

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
        if not allowlist:
            raise RuntimeError(
                "Instagram publishing blocked: IG_IMAGE_HOST_ALLOWLIST is empty. "
                "Set it to the host(s) (e.g. cdn.example.com) where you serve post images."
            )
        if candidate and not image_url:
            raise RuntimeError(
                f"Instagram image_prompt host not in IG_IMAGE_HOST_ALLOWLIST: {candidate}"
            )
        if not image_url:
            raise RuntimeError(
                "Instagram feed posts require a public image URL. "
                "Set post.image_prompt to an https URL on an allowlisted host."
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


class BlueskyPublisher:
    """Publishes a Bluesky post via AT Protocol XRPC endpoints.

    We persist the access token + repo DID to disk and reuse it between runs.
    If the token is expired (401), we login once and retry the publish.
    """

    platform = "bluesky"

    def publish(self, post: GeneratedPost) -> str:
        body = post.render()
        if settings.dry_run:
            logger.info("[DRY RUN] Bluesky post (%d chars):\n%s", len(body), body)
            return "dry-run"
        if not settings.bluesky_identifier or not settings.bluesky_app_password:
            raise RuntimeError("Bluesky credentials missing. See .env.example.")

        session = self._load_session() or self._create_session()
        try:
            uri = self._publish_record(
                access_jwt=session["accessJwt"],
                repo_did=session["did"],
                text=body,
            )
        except httpx.HTTPStatusError as err:
            if err.response.status_code != 401:
                raise
            logger.info("Bluesky session expired; refreshing session and retrying once")
            session = self._create_session()
            uri = self._publish_record(
                access_jwt=session["accessJwt"],
                repo_did=session["did"],
                text=body,
            )
        logger.info("Bluesky post published: %s", uri)
        return uri

    def _service(self) -> str:
        return settings.bluesky_service_url.rstrip("/")

    def _session_path(self) -> Path:
        return Path(settings.bluesky_session_file).expanduser()

    def _load_session(self) -> dict[str, str] | None:
        path = self._session_path()
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(payload, dict):
            return None
        access_jwt = payload.get("accessJwt")
        did = payload.get("did")
        if not isinstance(access_jwt, str) or not access_jwt:
            return None
        if not isinstance(did, str) or not did:
            return None
        return {"accessJwt": access_jwt, "did": did}

    def _save_session(self, session: dict[str, str]) -> None:
        path = self._session_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(session), encoding="utf-8")
        path.chmod(0o600)

    def _create_session(self) -> dict[str, str]:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{self._service()}/xrpc/com.atproto.server.createSession",
                json={
                    "identifier": settings.bluesky_identifier,
                    "password": settings.bluesky_app_password,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        access_jwt = data.get("accessJwt")
        did = data.get("did")
        if not isinstance(access_jwt, str) or not access_jwt:
            raise RuntimeError("Bluesky createSession response missing accessJwt")
        if not isinstance(did, str) or not did:
            raise RuntimeError("Bluesky createSession response missing did")
        session = {"accessJwt": access_jwt, "did": did}
        self._save_session(session)
        return session

    def _publish_record(self, *, access_jwt: str, repo_did: str, text: str) -> str:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{self._service()}/xrpc/com.atproto.repo.createRecord",
                headers={"Authorization": f"Bearer {access_jwt}"},
                json={
                    "repo": repo_did,
                    "collection": "app.bsky.feed.post",
                    "record": {
                        "$type": "app.bsky.feed.post",
                        "text": text,
                        "createdAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
        uri = data.get("uri")
        if not isinstance(uri, str) or not uri:
            raise RuntimeError("Bluesky createRecord response missing uri")
        return uri


_REGISTRY: dict[str, type[Publisher]] = {
    "linkedin": LinkedInPublisher,
    "x": XPublisher,
    "instagram": InstagramPublisher,
    "bluesky": BlueskyPublisher,
}


def get_publisher(platform: str) -> Publisher:
    try:
        return _REGISTRY[platform]()
    except KeyError as err:
        raise ValueError(f"Unknown platform: {platform}") from err
