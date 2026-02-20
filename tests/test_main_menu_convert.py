from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from scripts.cli.io import MenuIO
from scripts.cli.menu import run_menu


@pytest.fixture
def mock_convert_x_main() -> Mock:
    mock = Mock(return_value=0)
    return mock


@pytest.fixture
def mock_convert_y_main() -> Mock:
    mock = Mock(return_value=0)
    return mock


class FakeIO(MenuIO):
    def __init__(self, inputs: list[str], outputs: list[str] | None = None) -> None:
        super().__init__()
        self._inputs: list[str] = list(inputs)
        self.outputs: list[str] = [] if outputs is None else outputs

    def write(self, message: str) -> None:
        self.outputs.append(message)

    def read(self, prompt: str = "") -> str:
        if not self._inputs:
            raise EOFError("No more inputs")
        return self._inputs.pop(0)


def test_convert_x_csv_cancel_path(
    mock_convert_x_main: Mock,
) -> None:
    """Test cancel path for convert_x_csv entry."""
    inputs = ["convert_x_csv", "--out test.json", "n", "q"]
    io = FakeIO(inputs)

    with patch(
        "scripts.other.convert_x_csv_to_json.main",
        side_effect=mock_convert_x_main,
    ):
        exit_code = run_menu(io)

    assert exit_code == 0
    assert "Convert cancelled." in io.outputs
    assert any("Preview command:" in out for out in io.outputs)
    # Verify main was NOT called (only one mock expected from patch, but we check cancel didn't execute)
    assert mock_convert_x_main.call_count == 0


def test_convert_x_csv_confirm_path_with_args(
    mock_convert_x_main: Mock,
) -> None:
    """Test confirm path for convert_x_csv entry with extra argv."""
    inputs = ["convert_x_csv", "path/to/file.csv --out output.json", "y", "q"]
    io = FakeIO(inputs)

    with patch(
        "scripts.other.convert_x_csv_to_json.main",
        side_effect=mock_convert_x_main,
    ) as mock_main:
        exit_code = run_menu(io)

    assert exit_code == 0
    assert "Convert finished with exit code: 0" in io.outputs
    assert any(
        "Preview command: uv run python scripts/other/convert_x_csv_to_json.py" in out
        for out in io.outputs
    )
    # Verify main was called with parsed argv
    assert mock_main.call_count == 1
    called_argv = mock_main.call_args[0][0]
    assert called_argv == ["path/to/file.csv", "--out", "output.json"]


def test_convert_x_csv_confirm_path_no_args(
    mock_convert_x_main: Mock,
) -> None:
    """Test confirm path for convert_x_csv entry without extra argv."""
    inputs = ["convert_x_csv", "", "y", "q"]
    io = FakeIO(inputs)

    with patch(
        "scripts.other.convert_x_csv_to_json.main",
        side_effect=mock_convert_x_main,
    ) as mock_main:
        exit_code = run_menu(io)

    assert exit_code == 0
    assert "Convert finished with exit code: 0" in io.outputs
    assert (
        "Preview command: uv run python scripts/other/convert_x_csv_to_json.py"
        in io.outputs
    )
    # Verify main was called with empty argv
    assert mock_main.call_count == 1
    called_argv = mock_main.call_args[0][0]
    assert called_argv == []


def test_convert_y_csv_cancel_path(
    mock_convert_y_main: Mock,
) -> None:
    """Test cancel path for convert_y_csv entry."""
    inputs = ["convert_y_csv", "--type test", "n", "q"]
    io = FakeIO(inputs)

    with patch(
        "scripts.other.convert_y_csv_to_json.main",
        side_effect=mock_convert_y_main,
    ):
        exit_code = run_menu(io)

    assert exit_code == 0
    assert "Convert cancelled." in io.outputs
    assert any("Preview command:" in out for out in io.outputs)
    # Verify main was NOT called
    assert mock_convert_y_main.call_count == 0


def test_convert_y_csv_confirm_path_with_args(
    mock_convert_y_main: Mock,
) -> None:
    """Test confirm path for convert_y_csv entry with extra argv."""
    inputs = ["convert_y_csv", "file1.csv file2.csv --out-dir outputs", "y", "q"]
    io = FakeIO(inputs)

    with patch(
        "scripts.other.convert_y_csv_to_json.main",
        side_effect=mock_convert_y_main,
    ) as mock_main:
        exit_code = run_menu(io)

    assert exit_code == 0
    assert "Convert finished with exit code: 0" in io.outputs
    assert any(
        "Preview command: uv run python scripts/other/convert_y_csv_to_json.py" in out
        for out in io.outputs
    )
    # Verify main was called with parsed argv
    assert mock_main.call_count == 1
    called_argv = mock_main.call_args[0][0]
    assert called_argv == ["file1.csv", "file2.csv", "--out-dir", "outputs"]


def test_convert_y_csv_confirm_path_no_args(
    mock_convert_y_main: Mock,
) -> None:
    """Test confirm path for convert_y_csv entry without extra argv."""
    inputs = ["convert_y_csv", "", "y", "q"]
    io = FakeIO(inputs)

    with patch(
        "scripts.other.convert_y_csv_to_json.main",
        side_effect=mock_convert_y_main,
    ) as mock_main:
        exit_code = run_menu(io)

    assert exit_code == 0
    assert "Convert finished with exit code: 0" in io.outputs
    assert (
        "Preview command: uv run python scripts/other/convert_y_csv_to_json.py"
        in io.outputs
    )
    # Verify main was called with empty argv
    assert mock_main.call_count == 1
    called_argv = mock_main.call_args[0][0]
    assert called_argv == []


def test_convert_invalid_extra_argv(
    mock_convert_x_main: Mock,
) -> None:
    """Test invalid extra argv handling for convert_x_csv."""
    # Unclosed quote will cause shlex.split to fail
    inputs = ["convert_x_csv", 'file.csv --out "unclosed', "q", "q"]
    io = FakeIO(inputs)

    with patch(
        "scripts.other.convert_x_csv_to_json.main",
        side_effect=mock_convert_x_main,
    ):
        exit_code = run_menu(io)

    assert exit_code == 0
    assert any("Invalid selection: Invalid extra argv" in out for out in io.outputs)
    # Verify main was NOT called due to invalid argv
    assert mock_convert_x_main.call_count == 0


def test_convert_x_csv_empty_confirm_calls_main_with_default_yes(
    mock_convert_x_main: Mock,
) -> None:
    """Test that empty confirm (default YES) executes the script."""
    inputs = ["convert_x_csv", "", "", "q"]
    io = FakeIO(inputs)

    with patch(
        "scripts.other.convert_x_csv_to_json.main",
        side_effect=mock_convert_x_main,
    ) as mock_main:
        exit_code = run_menu(io)

    assert exit_code == 0
    assert "Convert finished with exit code: 0" in io.outputs
    assert (
        "Preview command: uv run python scripts/other/convert_x_csv_to_json.py"
        in io.outputs
    )
    assert mock_main.call_count == 1
    called_argv = mock_main.call_args[0][0]
    assert called_argv == []


def test_convert_continues_after_completion(
    mock_convert_x_main: Mock,
) -> None:
    """Test that menu loop continues after convert completes."""
    # Select convert_x_csv, confirm, then select convert_y_csv, cancel, then quit
    inputs = ["convert_x_csv", "", "y", "convert_y_csv", "", "n", "q"]
    io = FakeIO(inputs)

    with (
        patch(
            "scripts.other.convert_x_csv_to_json.main",
            side_effect=mock_convert_x_main,
        ) as mock_x_main,
        patch(
            "scripts.other.convert_y_csv_to_json.main",
            side_effect=lambda argv: 0,
        ) as mock_y_main,
    ):
        exit_code = run_menu(io)

    assert exit_code == 0
    assert mock_x_main.call_count == 1
    assert mock_y_main.call_count == 0
    # Both operations should be reflected in outputs
    assert "Convert finished with exit code: 0" in io.outputs
    assert "Convert cancelled." in io.outputs
