"""Shared dataclasses / pydantic models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PublishPlatform = Literal["linkedin", "x", "instagram"]
ContentPlatform = Literal[
    "linkedin",
    "x",
    "bluesky",
    "instagram",
    "steam",
    "discord",
    "tiktok",
    "youtube",
    "reddit",
    "jodel",
]
Platform = ContentPlatform
CreatorChannel = Literal[
    "steam",
    "discord",
    "tiktok",
    "youtube",
    "instagram",
    "linkedin",
    "reddit",
    "twitch",
    "jodel",
    "assembly",
    "lurkit",
    "keymailer",
    "epic",
    "gog",
]


class Brief(BaseModel):
    """Source material the generator turns into platform posts."""

    topic: str
    details: str = ""
    url: str | None = None
    call_to_action: str | None = None
    tags: list[str] = Field(default_factory=list)


class GeneratedPost(BaseModel):
    platform: Platform
    text: str
    hashtags: list[str] = Field(default_factory=list)
    image_prompt: str | None = None

    def render(self) -> str:
        tags = " ".join(f"#{t.lstrip('#')}" for t in self.hashtags)
        return f"{self.text}\n\n{tags}".strip() if tags else self.text


class PostBundle(BaseModel):
    brief: Brief
    posts: list[GeneratedPost]
