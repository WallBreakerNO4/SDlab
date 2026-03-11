from __future__ import annotations

from dataclasses import dataclass
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cli.io import MenuIO
from scripts.cli.menu import run_menu


class _FakePrompt:
    def __init__(self, value: object) -> None:
        self._value = value

    def ask(self) -> object:
        return self._value


@dataclass
class _FakeChoice:
    title: str
    value: str


class _FakeQuestionary:
    Choice = _FakeChoice

    def __init__(
        self, *, selects: list[object], texts: list[object], confirms: list[object]
    ) -> None:
        self._selects = iter(selects)
        self._texts = iter(texts)
        self._confirms = iter(confirms)

    def select(self, _message: str, *, choices: list[_FakeChoice]) -> _FakePrompt:
        _ = choices
        return _FakePrompt(next(self._selects))

    def text(self, _message: str, *, default: str = "") -> _FakePrompt:
        _ = default
        return _FakePrompt(next(self._texts))

    def confirm(self, _message: str, *, default: bool) -> _FakePrompt:
        _ = default
        return _FakePrompt(next(self._confirms))


def test_other_convert_x_uses_env_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONVERT_X_DEFAULT_CSV", "custom/x.csv")
    calls: list[list[str] | None] = []

    def _fake_convert_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr("scripts.other.convert_x_csv_to_json.main", _fake_convert_main)
    fake_questionary = _FakeQuestionary(
        selects=["other", "csv_to_yaml", "convert_x_csv", "__exit__"],
        texts=["custom/x.csv"],
        confirms=[True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(MenuIO(print_func=outputs.append))

    assert exit_code == 0
    assert calls == [["custom/x.csv"]]
    assert any(
        "预览命令: uv run python scripts/other/convert_x_csv_to_json.py custom/x.csv"
        in output
        for output in outputs
    )


def test_other_convert_y_can_use_manual_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str] | None] = []

    def _fake_convert_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 3

    monkeypatch.setattr("scripts.other.convert_y_csv_to_json.main", _fake_convert_main)
    fake_questionary = _FakeQuestionary(
        selects=["other", "csv_to_yaml", "convert_y_csv", "__exit__"],
        texts=["assets/y.csv"],
        confirms=[True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(MenuIO(print_func=outputs.append))

    assert exit_code == 0
    assert calls == [["assets/y.csv"]]
    assert "转换完成，退出码: 3" in outputs


def test_other_clear_r2_uses_bucket_target_from_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str] | None] = []
    captured_targets: list[str | None] = []

    def _fake_clear_bucket_main(argv: list[str] | None = None) -> int:
        captured.append(argv)
        captured_targets.append(os.environ.get("SDSLAB_R2_CLEAR_BUCKET_TARGET"))
        return 0

    monkeypatch.setattr("scripts.r2_upload.clear_bucket.main", _fake_clear_bucket_main)
    fake_questionary = _FakeQuestionary(
        selects=["other", "clear_r2", "private", "__exit__"],
        texts=[],
        confirms=[True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(MenuIO(print_func=outputs.append))

    assert exit_code == 0
    assert captured == [[]]
    assert captured_targets == ["private"]
    assert "清空目标: R2_PRIVATE_BUCKET" in outputs
    assert "清空完成，退出码: 0" in outputs
