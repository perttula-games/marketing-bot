from __future__ import annotations

import pytest

from nemo_marketing_bot.growth import (
    build_growth_plan,
    growth_plan_to_csv,
    growth_plan_to_markdown,
    parse_growth_channels,
)


def test_parse_growth_channels_supports_aliases() -> None:
    assert parse_growth_channels("bsky,twitter") == ["bluesky", "x"]


def test_parse_growth_channels_rejects_unknown_channel() -> None:
    with pytest.raises(ValueError):
        parse_growth_channels("linkedin")


def test_growth_plan_is_manual_and_bluesky_specific() -> None:
    plan = build_growth_plan(
        game_name="Kalma",
        positioning="PC first-person survival horror",
        audience="PC horror players",
        channels=["bluesky"],
        daily_follow_limit=12,
        daily_like_limit=7,
        daily_reply_limit=8,
    )

    assert plan.channels == ("bluesky",)
    assert "Here to connect" in plan.bio_cta
    assert any("Follow up to 12" in action.action for action in plan.actions)
    assert any("Leave up to 7 relevant likes" in action.action for action in plan.actions)
    assert any("write up to 8 thoughtful replies" in action.action.lower() for action in plan.actions)
    assert any("blueskyfeeds.com" in query for query in plan.targets[0].search_queries)


def test_growth_plan_markdown_includes_safety_rules() -> None:
    plan = build_growth_plan(channels=["bluesky"])
    markdown = growth_plan_to_markdown(plan)

    assert "Manual actions only" in markdown
    assert "Do not use follow-unfollow tactics" in markdown
    assert "Target Pools" in markdown


def test_growth_plan_csv_exports_actions() -> None:
    plan = build_growth_plan(channels=["x"])
    csv_text = growth_plan_to_csv(plan)

    assert "day,channel,action,goal,limit,evidence" in csv_text
    assert "x" in csv_text
    assert "thoughtful replies" in csv_text
