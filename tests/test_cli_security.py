from __future__ import annotations

from pathlib import Path

import pytest
import typer

from nemo_marketing_bot.cli import _reject_sensitive_output_path


@pytest.mark.parametrize(
    "path",
    [
        Path(".env"),
        Path(".env.production"),
        Path("/home/example/.ssh/id_ed25519"),
        Path("out/.ssh/authorized_keys"),
    ],
)
def test_reject_sensitive_output_paths(path: Path) -> None:
    with pytest.raises(typer.BadParameter):
        _reject_sensitive_output_path(path)


def test_allows_normal_output_path() -> None:
    _reject_sensitive_output_path(Path("out/creator-outreach.csv"))