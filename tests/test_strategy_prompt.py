from __future__ import annotations

from pathlib import Path

from nemo_marketing_bot.strategy import (
    DEFAULT_MARKETING_SYSTEM_PROMPT,
    build_generation_system_prompt,
    build_revision_system_prompt,
    load_editable_strategy_prompt,
    write_default_strategy_prompt,
)


def test_load_strategy_prompt_falls_back_when_missing(tmp_path: Path) -> None:
    assert load_editable_strategy_prompt(tmp_path / "missing.md") == DEFAULT_MARKETING_SYSTEM_PROMPT.strip()


def test_generation_prompt_includes_custom_strategy_and_contract(tmp_path: Path) -> None:
    prompt_path = tmp_path / "strategy.md"
    prompt_path.write_text("Use crisp creator-first Finnish launch copy.", encoding="utf-8")

    prompt = build_generation_system_prompt(prompt_path)

    assert "Use crisp creator-first Finnish launch copy." in prompt
    assert "Non-negotiable operating rules" in prompt
    assert "Respond only with valid JSON" in prompt


def test_revision_prompt_preserves_revision_contract(tmp_path: Path) -> None:
    prompt_path = tmp_path / "strategy.md"
    prompt_path.write_text("Sound practical and direct.", encoding="utf-8")

    prompt = build_revision_system_prompt(prompt_path)

    assert "Sound practical and direct." in prompt
    assert "Revision contract" in prompt
    assert "preserving the platform" in prompt


def test_write_default_strategy_prompt_does_not_overwrite_without_force(tmp_path: Path) -> None:
    prompt_path = tmp_path / "strategy.md"
    prompt_path.write_text("keep me", encoding="utf-8")

    target, wrote = write_default_strategy_prompt(prompt_path)

    assert target == prompt_path
    assert not wrote
    assert prompt_path.read_text(encoding="utf-8") == "keep me"