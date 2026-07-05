from __future__ import annotations

from nemo_marketing_bot.telegram_bot import _is_approved_actor


def test_private_allowed_chat_is_approved_without_user_allowlist() -> None:
    assert _is_approved_actor(
        chat_id=123,
        user_id=456,
        chat_type="private",
        allowed_chat_ids={123},
        allowed_user_ids=set(),
    )


def test_group_chat_requires_user_allowlist() -> None:
    assert not _is_approved_actor(
        chat_id=123,
        user_id=456,
        chat_type="group",
        allowed_chat_ids={123},
        allowed_user_ids=set(),
    )


def test_user_allowlist_must_match_when_configured() -> None:
    assert not _is_approved_actor(
        chat_id=123,
        user_id=999,
        chat_type="group",
        allowed_chat_ids={123},
        allowed_user_ids={456},
    )
    assert _is_approved_actor(
        chat_id=123,
        user_id=456,
        chat_type="group",
        allowed_chat_ids={123},
        allowed_user_ids={456},
    )