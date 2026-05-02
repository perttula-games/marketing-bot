"""Platform publishers for LinkedIn, X, and Instagram.

Each publisher implements `publish(post)` and raises on failure. They honour
`settings.dry_run` — when true, no network calls are made and the rendered post
is simply logged. This keeps the main flow safe to run end-to-end without live
API credentials.
"""

from __future__ import annotations

import json
import logging
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
import tweepy

from .config import ig_image_allowlist, settings
from .models import GeneratedPost
from .security import is_allowed_image_host

logger = logging.getLogger(__name__)

X_MAX_CHARS = 280


class MetaTagParser(HTMLParser):
    """Extract og:image, og:title, og:description from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.og_image: str | None = None
        self.og_title: str | None = None
        self.og_description: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            attr_dict = dict(attrs)
            prop = (attr_dict.get("property") or "").lower()
            content = attr_dict.get("content")
            if prop == "og:image" and content:
                self.og_image = content
            elif prop == "og:title" and content:
                self.og_title = content
            elif prop == "og:description" and content:
                self.og_description = content


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
    """Publishes a post to Bluesky via AT Protocol XRPC endpoints."""

    platform = "bluesky"

    def _service(self) -> str:
        return settings.bluesky_service_url.rstrip("/")

    def _session_path(self) -> Path:
        return Path(settings.bluesky_session_file).expanduser()

    def _save_session(self, data: dict[str, str]) -> None:
        path = self._session_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:  # noqa: BLE001 - session caching is best-effort
            logger.debug("Failed to write Bluesky session file", exc_info=True)

    def _load_session(self) -> dict[str, str] | None:
        path = self._session_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and all(k in data for k in ("accessJwt", "did")):
                return {"accessJwt": data["accessJwt"], "did": data["did"]}
        except Exception:  # noqa: BLE001 - if cache is bad, we'll re-login
            logger.debug("Ignoring invalid Bluesky session file", exc_info=True)
        return None

    def _fetch_link_preview(self, url: str, client: httpx.Client) -> dict[str, Any] | None:
        """Fetch og:image and metadata from URL for link preview."""
        try:
            resp = client.get(url, timeout=10, follow_redirects=True)
            resp.raise_for_status()
            html = resp.text
            
            # Parse og:image, og:title, og:description
            parser = MetaTagParser()
            parser.feed(html)
            
            if not parser.og_image:
                return None
            
            return {
                "uri": url,
                "image": parser.og_image,
                "title": parser.og_title or "",
                "description": parser.og_description or "",
            }
        except Exception as err:
            logger.debug("Failed to fetch link preview for %s: %s", url, err)
            return None

    def _upload_blob_from_url(self, auth_client: httpx.Client, access_jwt: str, image_url: str) -> dict[str, Any] | None:
        """Download image from URL and upload as blob to Bluesky."""
        try:
            # Use a separate client for image download to avoid connection pool conflicts
            with httpx.Client(timeout=15, follow_redirects=True) as img_client:
                img_resp = img_client.get(image_url)
                img_resp.raise_for_status()
                image_data = img_resp.content
                content_type = img_resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()

            if len(image_data) > 1_000_000:
                logger.warning("Image too large: %d bytes", len(image_data))
                return None

            logger.debug("Uploading blob: size=%d, mime_type=%s", len(image_data), content_type)

            blob_resp = auth_client.post(
                f"{self._service()}/xrpc/com.atproto.repo.uploadBlob",
                headers={"Authorization": f"Bearer {access_jwt}", "Content-Type": content_type},
                content=image_data,
            )
            blob_resp.raise_for_status()
            blob_data = blob_resp.json()
            logger.debug("Blob response: %s", blob_data)

            return blob_data.get("blob", blob_data)
        except httpx.HTTPStatusError as err:
            logger.warning("Blob upload failed HTTP %d: %s", err.response.status_code, err.response.text)
            return None
        except Exception as err:
            logger.warning("Blob upload failed: %s", err)
            return None

    def _create_session(self, client: httpx.Client) -> dict[str, str]:
        if not settings.bluesky_identifier or not settings.bluesky_app_password:
            raise RuntimeError("Bluesky credentials missing. Set BLUESKY_IDENTIFIER and BLUESKY_APP_PASSWORD.")

        resp = client.post(
            f"{self._service()}/xrpc/com.atproto.server.createSession",
            json={
                "identifier": settings.bluesky_identifier,
                "password": settings.bluesky_app_password,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        session = {
            "accessJwt": data["accessJwt"],
            "did": data["did"],
        }
        self._save_session(session)
        return session

    def _post_record(self, client: httpx.Client, access_jwt: str, did: str, body: str, embed: dict[str, Any] | None = None) -> str:
        """Post a record to Bluesky with facets for URL link detection and optional embed."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        # Build facets array for URLs so Bluesky recognizes and linkifies them
        facets = self._build_facets(body)
        
        record: dict[str, Any] = {
            "$type": "app.bsky.feed.post",
            "text": body,
            "createdAt": now,
        }
        if facets:
            record["facets"] = facets
        if embed:
            record["embed"] = embed
        
        resp = client.post(
            f"{self._service()}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {access_jwt}"},
            json={
                "repo": did,
                "collection": "app.bsky.feed.post",
                "record": record,
            },
        )
        resp.raise_for_status()
        out = resp.json()
        return out.get("uri") or out.get("cid") or "ok"

    def _build_facets(self, text: str) -> list[dict[str, Any]]:
        """Extract URLs from text and build Bluesky facets array for link detection."""
        # Find all URLs in the text
        url_pattern = re.compile(r"https?://[^\s]+")
        facets = []
        
        for match in url_pattern.finditer(text):
            url = match.group(0)
            # Remove trailing punctuation that's not part of the URL
            while url and url[-1] in ",.;:!?)\"'":
                url = url[:-1]
            
            start_byte = len(text[:match.start()].encode("utf-8"))
            # For end byte, we need to account for the potential truncation
            end_byte = start_byte + len(url.encode("utf-8"))
            
            facets.append({
                "index": {
                    "byteStart": start_byte,
                    "byteEnd": end_byte,
                },
                "features": [
                    {
                        "$type": "app.bsky.richtext.facet#link",
                        "uri": url,
                    }
                ],
            })
        
        return facets

    def publish(self, post: GeneratedPost) -> str:
        body = post.render()
        if settings.dry_run:
            logger.info("[DRY RUN] Bluesky post (%d chars):\n%s", len(body), body)
            return "dry-run"

        with httpx.Client(timeout=30) as client:
            # Always create a fresh session to avoid expired token issues during blob upload
            session = self._create_session(client)

            # Try to fetch link preview if there's a URL in the body
            embed = None
            url_match = re.search(r"https?://\S+", body)
            if url_match:
                url = url_match.group(0).rstrip(".,;:!?)'\"")
                link_preview = self._fetch_link_preview(url, client)
                if link_preview and link_preview.get("image"):
                    blob = self._upload_blob_from_url(client, session["accessJwt"], link_preview["image"])
                    if blob:
                        logger.info("Bluesky link preview embed created for %s", url)
                        embed = {
                            "$type": "app.bsky.embed.external",
                            "external": {
                                "uri": link_preview["uri"],
                                "title": link_preview.get("title", ""),
                                "description": link_preview.get("description", ""),
                                "thumb": blob,
                            },
                        }
                    else:
                        logger.warning("Blob upload failed, posting without image preview")

            publish_id = self._post_record(client, session["accessJwt"], session["did"], body, embed)

        logger.info("Bluesky post published: %s", publish_id)
        return publish_id


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
