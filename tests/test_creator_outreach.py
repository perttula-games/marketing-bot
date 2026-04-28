from __future__ import annotations

import pytest

from nemo_marketing_bot.creator_outreach import (
    build_creator_plan,
    creator_plan_to_csv,
    parse_creator_channels,
)


def test_parse_creator_channels_supports_practical_aliases() -> None:
    assert parse_creator_channels("shorts,reels,yt") == ["youtube", "instagram"]


def test_parse_creator_channels_rejects_unknown_channel() -> None:
    with pytest.raises(ValueError):
        parse_creator_channels("fax")


def test_creator_plan_includes_manual_setup_and_targets() -> None:
    plan = build_creator_plan(
        game_name="NemoClaw",
        genre="co-op action roguelite",
        audience="PC players",
        budget="organic-first",
        language="fi,en",
        store_url="https://store.steampowered.com/app/example",
        discord_url="https://discord.gg/example",
        channels=["tiktok", "youtube"],
    )

    assert {task.channel for task in plan.setup_tasks} >= {"steam", "discord", "tiktok", "youtube"}
    assert [target.channel for target in plan.creator_targets] == ["tiktok", "youtube"]
    assert "NemoClaw" in plan.outreach_templates["creator_dm_en"]


def test_creator_plan_csv_exports_tracking_columns() -> None:
    plan = build_creator_plan(
        game_name="NemoClaw",
        genre="co-op action roguelite",
        audience="PC players",
        budget="organic-first",
        language="fi,en",
        store_url=None,
        discord_url=None,
        channels=["tiktok"],
    )

    csv_text = creator_plan_to_csv(plan)

    assert "channel,priority,target_profile" in csv_text
    assert "tiktok" in csv_text
    assert "wishlists or demo installs" in csv_text