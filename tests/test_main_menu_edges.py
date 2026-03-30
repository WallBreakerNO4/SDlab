from __future__ import annotations

from dataclasses import dataclass
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
        if isinstance(self._value, BaseException):
            raise self._value
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


def test_run_menu_keyboard_interrupt_returns_130(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_questionary = _FakeQuestionary(
        selects=[KeyboardInterrupt()], texts=[], confirms=[]
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    assert run_menu(MenuIO(print_func=lambda _message: None)) == 130


def test_run_menu_none_result_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_questionary = _FakeQuestionary(selects=[None], texts=[], confirms=[])
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    assert run_menu(MenuIO(print_func=lambda _message: None)) == 0


def test_generate_cancelled_before_execution_does_not_call_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = {"value": False}

    def _fake_generate_main(argv: list[str] | None = None) -> int:
        _ = argv
        called["value"] = True
        return 0

    monkeypatch.setattr(
        "scripts.generation.comfyui_part1_generate.main", _fake_generate_main
    )
    fake_questionary = _FakeQuestionary(
        selects=["generate", "data/runs/example/config.yaml", "__exit__"],
        texts=[],
        confirms=[False, False],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    assert run_menu(MenuIO(print_func=lambda _message: None)) == 0
    assert called["value"] is False
