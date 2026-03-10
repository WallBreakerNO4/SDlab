from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path

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


def test_run_menu_can_execute_multiple_actions_before_exit(monkeypatch) -> None:
    x_calls: list[list[str] | None] = []
    y_calls: list[list[str] | None] = []

    monkeypatch.setattr(
        "scripts.other.convert_x_csv_to_json.main",
        lambda argv=None: x_calls.append(argv) or 0,
    )
    monkeypatch.setattr(
        "scripts.other.convert_y_csv_to_json.main",
        lambda argv=None: y_calls.append(argv) or 0,
    )
    fake_questionary = _FakeQuestionary(
        selects=[
            "other",
            "csv_to_yaml",
            "convert_x_csv",
            "other",
            "csv_to_yaml",
            "convert_y_csv",
            "__exit__",
        ],
        texts=["x.csv", "y.csv"],
        confirms=[True, True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    assert run_menu(MenuIO(print_func=lambda _message: None)) == 0
    assert x_calls == [["x.csv"]]
    assert y_calls == [["y.csv"]]
