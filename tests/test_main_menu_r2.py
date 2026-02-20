"""Test R2 upload menu integration."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import override

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.cli.io import MenuIO
from scripts.cli.menu import run_menu


class DummyMenuIO(MenuIO):
    """Simple in-memory MenuIO for testing."""

    inputs: list[str]
    outputs: list[str]
    input_index: int

    def __init__(self, inputs: list[str]) -> None:
        super().__init__()
        self.inputs = list(inputs)
        self.outputs = []
        self.input_index = 0

    @override
    def read(self, prompt: str = "") -> str:
        if self.input_index >= len(self.inputs):
            raise EOFError()
        value = self.inputs[self.input_index]
        self.input_index += 1
        return value

    @override
    def write(self, message: str) -> None:
        self.outputs.append(message)


def test_r2_upload_menu_entry_is_selectable() -> None:
    """Test that R2 upload entry appears in menu and can be selected."""
    from scripts.cli.registry import iter_entries

    entries = list(iter_entries(include_disabled=True))
    r2_entry = next((e for e in entries if e.key == "upload_r2"), None)

    assert r2_entry is not None, "R2 upload entry should exist"
    assert r2_entry.label == "Upload images to R2"
    assert r2_entry.entrypoint == "scripts.r2_upload.upload_images_to_r2:main"
    assert r2_entry.enabled is True, "R2 upload should be enabled"


def test_r2_upload_prompts_extra_argv_and_shows_preview() -> None:
    """Test that selecting R2 upload prompts for extra argv and shows preview command."""
    io = DummyMenuIO(["4", "--help", "n", "q"])
    exit_code = run_menu(io)

    assert exit_code == 0
    assert len(io.outputs) > 0

    preview_command = "uv run python scripts/r2_upload/upload_images_to_r2.py --help"
    assert any(
        "Preview command:" in output and preview_command in output
        for output in io.outputs
    ), f"Should show preview command with extra argv: {preview_command}"


def test_r2_upload_selection_by_key_with_extra_argv() -> None:
    """Test that R2 upload can be selected by key with extra argv."""
    io = DummyMenuIO(["upload_r2", "--run-dir .sisyphus/test", "n", "q"])
    exit_code = run_menu(io)

    assert exit_code == 0

    preview_command = "uv run python scripts/r2_upload/upload_images_to_r2.py --run-dir .sisyphus/test"
    assert any(
        "Preview command:" in output and preview_command in output
        for output in io.outputs
    ), "Should show preview command when selecting by key"


def test_r2_upload_with_empty_extra_argv() -> None:
    """Test that R2 upload works with empty extra argv."""
    io = DummyMenuIO(["4", "", "n", "q"])
    exit_code = run_menu(io)

    assert exit_code == 0

    preview_command = "uv run python scripts/r2_upload/upload_images_to_r2.py"
    assert any(
        "Preview command:" in output and preview_command in output
        for output in io.outputs
    ), "Should show base command with no extra argv"


def test_r2_upload_invalid_extra_argv_returns_to_menu() -> None:
    """Test that invalid extra argv shows error and returns to menu."""
    io = DummyMenuIO(["4", "'unclosed", "q"])
    exit_code = run_menu(io)

    assert exit_code == 0

    assert any(
        "Invalid selection: Invalid extra argv" in output for output in io.outputs
    ), "Should show error for invalid extra argv"


def test_r2_upload_returns_to_menu_loop_after_cancel() -> None:
    """Test that after R2 upload cancellation, menu continues to work."""
    inputs = ["4", "--help", "n", "2", "n", "q"]
    io = DummyMenuIO(inputs)
    exit_code = run_menu(io)

    assert exit_code == 0

    menu_lines_count = sum(1 for output in io.outputs if "Available scripts:" in output)
    assert menu_lines_count >= 2, (
        "Menu should be displayed multiple times (after R2, after convert_x)"
    )


def test_r2_upload_extra_argv_with_spaces() -> None:
    """Test that extra argv with spaces are properly parsed via shlex."""
    io = DummyMenuIO(["4", '--run-dir ".sisyphus/some path"', "n", "q"])
    exit_code = run_menu(io)

    assert exit_code == 0

    assert any("Preview command:" in output for output in io.outputs), (
        "Should show preview command"
    )
    assert any(
        "Preview command:" in output and ".sisyphus/some path" in output
        for output in io.outputs
    ), "Should preserve spaces in extra argv through preview command"
