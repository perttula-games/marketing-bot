from __future__ import annotations

from nemo_marketing_bot.generator import _build_user_prompt
from nemo_marketing_bot.models import Brief, GeneratedPost, PostBundle
from nemo_marketing_bot.pipeline import publish_bundle


def test_prompt_includes_manual_content_channel_rules() -> None:
    prompt = _build_user_prompt(
        Brief(topic="Demo reveal", details="Show a new combat mechanic."),
        ["tiktok", "youtube", "steam", "bluesky"],
    )

    assert "TikTok / Reels / Shorts short-form video script" in prompt
    assert "YouTube asset draft" in prompt
    assert "Steam Event / Announcement" in prompt
    assert "Bluesky post" in prompt
    assert '"platform": "tiktok|youtube|steam|bluesky"' in prompt


def test_publish_bundle_skips_manual_channels() -> None:
    bundle = PostBundle(
        brief=Brief(topic="Demo reveal"),
        posts=[GeneratedPost(platform="bluesky", text="Kalma first look")],
    )

    assert publish_bundle(bundle) == {"bluesky": "manual: no API publisher configured"}


def test_publish_bundle_blocks_repost_like_content() -> None:
    bundle = PostBundle(
        brief=Brief(topic="Community repost"),
        posts=[GeneratedPost(platform="x", text="RT @creator Great insights")],
    )

    assert publish_bundle(bundle) == {"x": "blocked: repost/quote-post markers are not allowed"}
