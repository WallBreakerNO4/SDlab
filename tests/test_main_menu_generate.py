from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cli.io import MenuIO
from scripts.cli.menu import run_menu


def _build_menu_io(
    steps: list[str],
    events: list[tuple[str, object]],
) -> MenuIO:
    iterator = iter(steps)

    def _input(_prompt: str = "") -> str:
        return next(iterator)

    def _print(message: str) -> None:
        events.append(("print", message))

    return MenuIO(input_func=_input, print_func=_print)


def _printed_messages(events: list[tuple[str, object]]) -> list[str]:
    messages: list[str] = []
    for kind, payload in events:
        if kind != "print":
            continue
        if isinstance(payload, str):
            messages.append(payload)
    return messages


def test_menu_generate_cancel_does_not_call_main(
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

    events: list[tuple[str, object]] = []
    io = _build_menu_io(["1", "", "n", "q"], events)

    exit_code = run_menu(io)

    assert exit_code == 0
    assert calls == []
    printed = _printed_messages(events)
    assert (
        "Preview command: uv run python scripts/generation/comfyui_part1_generate.py"
        in printed
    )
    assert "Generation cancelled." in printed


def test_menu_generate_confirm_calls_main_once_with_shlex_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str] | None] = []

    def _fake_generate_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 7

    monkeypatch.setattr(
        "scripts.generation.comfyui_part1_generate.main",
        _fake_generate_main,
    )

    events: list[tuple[str, object]] = []
    io = _build_menu_io(["generate_grid", "--dry-run --x-limit 2", "yes", "q"], events)

    exit_code = run_menu(io)

    assert exit_code == 0
    assert calls == [["--dry-run", "--x-limit", "2"]]
    printed = _printed_messages(events)
    assert (
        "Preview command: uv run python scripts/generation/comfyui_part1_generate.py --dry-run --x-limit 2"
        in printed
    )
    assert "Generation finished with exit code: 7" in printed


def test_menu_generate_preview_is_printed_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, object]] = []

    def _fake_generate_main(argv: list[str] | None = None) -> int:
        events.append(("call", argv))
        return 0

    monkeypatch.setattr(
        "scripts.generation.comfyui_part1_generate.main",
        _fake_generate_main,
    )

    io = _build_menu_io(["1", "--dry-run", "y", "q"], events)

    exit_code = run_menu(io)

    assert exit_code == 0
    preview_index = next(
        index
        for index, event in enumerate(events)
        if event
        == (
            "print",
            "Preview command: uv run python scripts/generation/comfyui_part1_generate.py --dry-run",
        )
    )
    call_index = next(index for index, event in enumerate(events) if event[0] == "call")
    assert preview_index < call_index


def test_menu_generate_empty_confirm_calls_main_with_default_yes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that empty confirm (default YES) executes the script."""
    calls: list[list[str] | None] = []

    def _fake_generate_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(
        "scripts.generation.comfyui_part1_generate.main",
        _fake_generate_main,
    )

    events: list[tuple[str, object]] = []
    # Empty string for confirm triggers default YES
    io = _build_menu_io(["generate_grid", "", "", "q"], events)

    exit_code = run_menu(io)

    assert exit_code == 0
    assert calls == [[]]
    printed = _printed_messages(events)
    assert (
        "Preview command: uv run python scripts/generation/comfyui_part1_generate.py"
        in printed
    )
    assert "Generation finished with exit code: 0" in printed


def test_menu_generate_unknown_confirm_cancels_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that unknown confirm input (e.g., 'maybe') cancels and does not call main."""
    calls: list[list[str] | None] = []

    def _fake_generate_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(
        "scripts.generation.comfyui_part1_generate.main",
        _fake_generate_main,
    )

    events: list[tuple[str, object]] = []
    # Unknown input 'maybe' for confirm should cancel
    io = _build_menu_io(["generate_grid", "", "maybe", "q"], events)

    exit_code = run_menu(io)

    assert exit_code == 0
    assert calls == []
    printed = _printed_messages(events)
    assert (
        "Preview command: uv run python scripts/generation/comfyui_part1_generate.py"
        in printed
    )
    assert "Invalid confirmation, cancelled." in printed
