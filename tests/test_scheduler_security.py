from __future__ import annotations

import pytest

from nemo_marketing_bot.scheduler import _scheduled_auto_publish_enabled


def test_scheduled_auto_publish_rejects_string_false() -> None:
    with pytest.raises(ValueError, match="auto_publish must be boolean"):
        _scheduled_auto_publish_enabled("false", job_name="rss")


def test_scheduled_auto_publish_false_is_false() -> None:
    assert not _scheduled_auto_publish_enabled(False, job_name="rss")


def test_scheduled_auto_publish_requires_env_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nemo_marketing_bot.scheduler.settings.allow_scheduled_autopublish", False)

    assert not _scheduled_auto_publish_enabled(True, job_name="rss")


def test_scheduled_auto_publish_allows_true_when_env_gate_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nemo_marketing_bot.scheduler.settings.allow_scheduled_autopublish", True)

    assert _scheduled_auto_publish_enabled(True, job_name="rss")