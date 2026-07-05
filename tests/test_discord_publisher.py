from __future__ import annotations

from nemo_marketing_bot.models import GeneratedPost
from nemo_marketing_bot.publishers import DiscordPublisher


def test_discord_payload_includes_embed_image_and_link_button() -> None:
    post = GeneratedPost(
        platform="discord",
        text="Patch 0.4 Live\nNew co-op fixes and smoother movement.",
        hashtags=["NemoClaw"],
        image_prompt="https://cdn.example.com/patch-04.png",
    )
    post.text += "\nRead more: https://example.com/news"

    payload = DiscordPublisher()._build_payload(post)

    assert payload["content"].startswith("Patch 0.4 Live")
    assert payload["allowed_mentions"] == {"parse": []}
    assert "flags" not in payload
    assert payload["embeds"][0]["image"]["url"] == "https://cdn.example.com/patch-04.png"
    assert payload["components"][0]["components"][0]["url"] == "https://example.com/news"


def test_discord_payload_omits_button_when_no_url() -> None:
    post = GeneratedPost(platform="discord", text="Patch note\nShort update.", hashtags=[])

    payload = DiscordPublisher()._build_payload(post)

    assert "flags" not in payload
    assert "embeds" not in payload
    assert "components" not in payload


def test_discord_url_extraction_trims_trailing_punctuation() -> None:
    url = DiscordPublisher()._extract_first_url("Read this (https://example.com/page).")
    assert url == "https://example.com/page"
