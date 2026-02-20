from __future__ import annotations

import sys
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cli.io import MenuIO
from scripts.cli.menu import run_menu


def _build_menu_io(
    steps: list[tuple[str, str | BaseException]],
    events: list[str],
) -> MenuIO:
    iterator = iter(steps)

    def _input(prompt: str = "") -> str:
        expected_prompt, payload = next(iterator)
        assert prompt == expected_prompt
        if isinstance(payload, BaseException):
            raise payload
        return payload

    def _print(message: str) -> None:
        events.append(message)

    return MenuIO(input_func=_input, print_func=_print)


def test_ctrl_d_at_extra_argv_prompt_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str] | None] = []

    def _fake_generate_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(
        "scripts.generation.comfyui_part1_generate.main",
        _fake_generate_main,
    )

    events: list[str] = []
    io = _build_menu_io(
        [
            ("Select an option: ", "generate_grid"),
            ("Extra argv (optional): ", EOFError()),
        ],
        events,
    )

    exit_code = run_menu(io)

    assert exit_code == 0
    assert calls == []


def test_ctrl_c_at_confirm_prompt_returns_130(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str] | None] = []

    def _fake_generate_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(
        "scripts.generation.comfyui_part1_generate.main",
        _fake_generate_main,
    )

    events: list[str] = []
    io = _build_menu_io(
        [
            ("Select an option: ", "generate_grid"),
            ("Extra argv (optional): ", "--dry-run"),
            ("Confirm execution? [Y/n]: ", KeyboardInterrupt()),
        ],
        events,
    )

    exit_code = run_menu(io)

    assert exit_code == 130
    assert calls == []


def test_system_exit_zero_is_handled_and_menu_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_generate_main(_argv: list[str] | None = None) -> int:
        raise SystemExit(0)

    monkeypatch.setattr(
        "scripts.generation.comfyui_part1_generate.main",
        _fake_generate_main,
    )

    events: list[str] = []
    io = _build_menu_io(
        [
            ("Select an option: ", "generate_grid"),
            ("Extra argv (optional): ", "--help"),
            ("Confirm execution? [Y/n]: ", "y"),
            ("Select an option: ", "q"),
        ],
        events,
    )

    exit_code = run_menu(io)

    assert exit_code == 0
    assert "Script exited with exit code: 0" in events
    assert events.count("Available scripts:") >= 2


def test_system_exit_nonzero_is_handled_and_menu_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_convert_main(_argv: list[str] | None = None) -> int:
        raise SystemExit(2)

    convert_x_module = importlib.import_module("scripts.other.convert_x_csv_to_json")
    monkeypatch.setattr(convert_x_module, "main", _fake_convert_main)

    events: list[str] = []
    io = _build_menu_io(
        [
            ("Select an option: ", "convert_x_csv"),
            ("Extra argv (optional): ", "--help"),
            ("Confirm execution? [Y/n]: ", "yes"),
            ("Select an option: ", "q"),
        ],
        events,
    )

    exit_code = run_menu(io)

    assert exit_code == 0
    assert "Script exited with exit code: 2" in events
    assert events.count("Available scripts:") >= 2


def test_unexpected_exception_is_controlled_and_menu_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_convert_main(_argv: list[str] | None = None) -> int:
        raise RuntimeError("boom")

    convert_y_module = importlib.import_module("scripts.other.convert_y_csv_to_json")
    monkeypatch.setattr(convert_y_module, "main", _fake_convert_main)

    events: list[str] = []
    io = _build_menu_io(
        [
            ("Select an option: ", "convert_y_csv"),
            ("Extra argv (optional): ", ""),
            ("Confirm execution? [Y/n]: ", "y"),
            ("Select an option: ", "q"),
        ],
        events,
    )

    exit_code = run_menu(io)

    assert exit_code == 0
    assert "Script execution failed: boom" in events
    assert "Traceback" not in "\n".join(events)
    assert events.count("Available scripts:") >= 2
