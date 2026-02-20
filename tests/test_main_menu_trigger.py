from __future__ import annotations

import builtins
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main as main_module
import pytest


class _TTYStream:
    def __init__(self, is_tty: bool) -> None:
        self._is_tty: bool = is_tty
        self._chunks: list[str] = []

    def isatty(self) -> bool:
        return self._is_tty

    def write(self, text: str) -> int:
        self._chunks.append(text)
        return len(text)

    def flush(self) -> None:
        return None

    def getvalue(self) -> str:
        return "".join(self._chunks)


def _patch_stdio_tty(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stdin_tty: bool,
    stdout_tty: bool,
) -> _TTYStream:
    stdin_stream = _TTYStream(stdin_tty)
    stdout_stream = _TTYStream(stdout_tty)
    monkeypatch.setattr(sys, "stdin", stdin_stream)
    monkeypatch.setattr(sys, "stdout", stdout_stream)
    return stdout_stream


def test_main_no_args_and_tty_enters_menu_and_can_quit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _patch_stdio_tty(monkeypatch, stdin_tty=True, stdout_tty=True)

    def _input_quit(_prompt: str = "") -> str:
        return "q"

    monkeypatch.setattr(builtins, "input", _input_quit)

    called = {"generate": False}

    def _fake_generate(_argv: list[str] | None) -> int:
        called["generate"] = True
        return 99

    monkeypatch.setattr(main_module, "generate_main", _fake_generate)

    exit_code = main_module.main([])

    assert exit_code == 0
    assert called["generate"] is False


def test_main_menu_flag_tty_forces_menu_even_with_other_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout_stream = _patch_stdio_tty(monkeypatch, stdin_tty=True, stdout_tty=True)

    def _input_quit(_prompt: str = "") -> str:
        return "q"

    monkeypatch.setattr(builtins, "input", _input_quit)

    called = {"generate": False}

    def _fake_generate(_argv: list[str] | None) -> int:
        called["generate"] = True
        return 99

    monkeypatch.setattr(main_module, "generate_main", _fake_generate)

    exit_code = main_module.main(["--menu", "--help"])

    assert exit_code == 0
    assert called["generate"] is False
    assert "extra args are ignored in menu mode" in stdout_stream.getvalue()


def test_main_menu_generate_cancel_returns_to_loop_and_does_not_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout_stream = _patch_stdio_tty(monkeypatch, stdin_tty=True, stdout_tty=True)

    steps = iter(["1", "", "n", "q"])

    def _input_select_generate_then_quit(_prompt: str = "") -> str:
        return next(steps)

    monkeypatch.setattr(builtins, "input", _input_select_generate_then_quit)

    called = {"generate": False}

    def _fake_generate(_argv: list[str] | None) -> int:
        called["generate"] = True
        return 99

    monkeypatch.setattr(main_module, "generate_main", _fake_generate)

    exit_code = main_module.main(["--menu"])

    assert exit_code == 0
    assert called["generate"] is False
    assert (
        "Preview command: uv run python scripts/generation/comfyui_part1_generate.py"
        in stdout_stream.getvalue()
    )
    assert "Generation cancelled." in stdout_stream.getvalue()


def test_main_menu_flag_non_tty_prints_reason_and_returns_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout_stream = _patch_stdio_tty(monkeypatch, stdin_tty=False, stdout_tty=False)

    def _unexpected_input(_prompt: str = "") -> str:
        raise AssertionError("input() should not be called for --menu in non-TTY")

    monkeypatch.setattr(builtins, "input", _unexpected_input)

    called = {"generate": False}

    def _fake_generate(_argv: list[str] | None) -> int:
        called["generate"] = True
        return 99

    monkeypatch.setattr(main_module, "generate_main", _fake_generate)

    exit_code = main_module.main(["--menu"])

    assert exit_code == 2
    assert called["generate"] is False
    assert "--menu requires an interactive TTY" in stdout_stream.getvalue()


def test_main_passthrough_when_non_menu_args_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _patch_stdio_tty(monkeypatch, stdin_tty=True, stdout_tty=True)

    captured: dict[str, list[str] | None] = {"argv": None}

    def _fake_generate(argv: list[str] | None) -> int:
        captured["argv"] = argv
        return 7

    monkeypatch.setattr(main_module, "generate_main", _fake_generate)

    exit_code = main_module.main(["--dry-run", "--x-limit", "1"])

    assert exit_code == 7
    assert captured["argv"] == ["--dry-run", "--x-limit", "1"]


def test_main_passthrough_keeps_none_argv_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _patch_stdio_tty(monkeypatch, stdin_tty=False, stdout_tty=False)
    monkeypatch.setattr(sys, "argv", ["main.py", "--dry-run"])

    captured: dict[str, list[str] | None | str] = {"argv": "sentinel"}

    def _fake_generate(argv: list[str] | None) -> int:
        captured["argv"] = argv
        return 11

    monkeypatch.setattr(main_module, "generate_main", _fake_generate)

    exit_code = main_module.main(None)

    assert exit_code == 11
    assert captured["argv"] is None
