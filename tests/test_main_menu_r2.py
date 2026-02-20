"""Test R2 upload menu placeholder behavior."""

from __future__ import annotations

import importlib
from typing import override
from unittest.mock import patch

import pytest

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


def test_r2_upload_selection_shows_placeholder_message() -> None:
    """Test that selecting R2 upload shows controlled message without importing R2 module."""
    original_import_module = importlib.import_module

    def blocked_import_module(name: str, *args: str, **kwargs: str) -> object:
        if "scripts.r2_upload.upload_images_to_r2" in name:
            pytest.fail(
                f"R2 upload module should NOT be imported, but tried to import: {name}"
            )
        return original_import_module(name)

    with patch.object(importlib, "import_module", side_effect=blocked_import_module):
        io = DummyMenuIO(["4", "q"])
        exit_code = run_menu(io)

    assert exit_code == 0
    assert len(io.outputs) > 0

    preview_command = "uv run python scripts/r2_upload/upload_images_to_r2.py"
    assert any(
        "Preview command:" in output and preview_command in output
        for output in io.outputs
    ), f"Should show preview command for R2 upload"

    assert any("未实现" in output for output in io.outputs), (
        "Should show '未实现' message"
    )

    assert all(
        "Traceback (most recent call last)" not in output
        and "NotImplementedError" not in output
        for output in io.outputs
    ), "Should NOT show traceback or NotImplementedError"


def test_r2_upload_selection_by_key() -> None:
    """Test that R2 upload can be selected by key 'upload_r2'."""
    original_import_module = importlib.import_module

    def blocked_import_module(name: str, *args: str, **kwargs: str) -> object:
        if "scripts.r2_upload.upload_images_to_r2" in name:
            pytest.fail(
                f"R2 upload module should NOT be imported, but tried to import: {name}"
            )
        return original_import_module(name)

    with patch.object(importlib, "import_module", side_effect=blocked_import_module):
        io = DummyMenuIO(["upload_r2", "q"])
        exit_code = run_menu(io)

    assert exit_code == 0

    preview_command = "uv run python scripts/r2_upload/upload_images_to_r2.py"
    assert any(
        "Preview command:" in output and preview_command in output
        for output in io.outputs
    ), "Should show preview command when selecting by key"

    assert any("未实现" in output for output in io.outputs), (
        "Should show '未实现' message when selecting by key"
    )


def test_r2_upload_does_not_call_main() -> None:
    """Test that R2 upload main() is never called."""
    with patch("scripts.r2_upload.upload_images_to_r2.main") as mock_main:
        mock_main.side_effect = AssertionError("R2 main() should NOT be called")
        io = DummyMenuIO(["4", "q"])
        exit_code = run_menu(io)

    assert exit_code == 0
    assert not mock_main.called, "R2 main() should never be called"


def test_r2_upload_returns_to_menu_loop() -> None:
    """Test that after R2 upload placeholder, we can still interact with menu."""
    inputs = ["4", "2", "n", "q"]
    io = DummyMenuIO(inputs)

    # Monkeypatch importlib to prevent R2 module import
    original_import_module = importlib.import_module

    def blocked_import_module(name: str, *args: str, **kwargs: str) -> object:
        if "scripts.r2_upload.upload_images_to_r2" in name:
            pytest.fail(
                f"R2 upload module should NOT be imported, but tried to import: {name}"
            )
        return original_import_module(name)

    with patch.object(importlib, "import_module", side_effect=blocked_import_module):
        exit_code = run_menu(io)

    assert exit_code == 0

    # Should have multiple menu displays (R2 upload + convert_x_csv)
    menu_lines_count = sum(1 for output in io.outputs if "Available scripts:" in output)
    assert menu_lines_count >= 2, (
        "Menu should be displayed multiple times (after R2, after convert_x)"
    )
