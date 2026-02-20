from __future__ import annotations

import builtins
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cli.io import MenuIO
from scripts.cli.menu import run_menu


def _patch_input_steps(
    monkeypatch: pytest.MonkeyPatch,
    steps: list[str | BaseException],
) -> None:
    iterator = iter(steps)

    def _input(_prompt: str = "") -> str:
        step = next(iterator)
        if isinstance(step, BaseException):
            raise step
        return step

    monkeypatch.setattr(builtins, "input", _input)


def test_run_menu_reprompts_after_invalid_inputs_until_quit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_input_steps(monkeypatch, ["", "unknown", "999", "q"])

    exit_code = run_menu(MenuIO())

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.count("Available scripts:") == 4
    assert "Invalid selection: Empty choice" in captured.out
    assert "Invalid selection: Unknown choice" in captured.out
    assert "Invalid selection: Choice out of range" in captured.out


def test_run_menu_eoferror_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_input_steps(monkeypatch, [EOFError()])

    exit_code = run_menu(MenuIO())

    assert exit_code == 0


def test_run_menu_keyboardinterrupt_returns_130(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_input_steps(monkeypatch, [KeyboardInterrupt()])

    exit_code = run_menu(MenuIO())

    assert exit_code == 130


def test_run_menu_prints_usage_hints_on_startup(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_input_steps(monkeypatch, ["q"])

    exit_code = run_menu(MenuIO())

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "提示：无参+TTY 自动进入菜单；带参时透传到生图脚本。" in captured.out
    assert "提示：使用 --menu 强制进入菜单；非 TTY 会拒绝并提示。" in captured.out
    assert "提示：选择脚本后会打印可复制命令模板，并二次确认。" in captured.out
