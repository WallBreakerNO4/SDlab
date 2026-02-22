# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportPrivateUsage=false, reportUnusedCallResult=false

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from scripts.generation.retry_failed_selection import (
    _image_exists,
    _load_latest_records_strict,
    select_failed_and_incomplete_cells,
)


def test_select_empty_metadata_returns_all_incomplete(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.jsonl"
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    expected_cells = {(0, 0), (0, 1), (1, 0), (1, 1)}

    result = select_failed_and_incomplete_cells(metadata_path, run_dir, expected_cells)

    assert result.failed_cells == []
    assert result.incomplete_cells == [(0, 0), (0, 1), (1, 0), (1, 1)]


def test_select_failed_cells(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.jsonl"
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    expected_cells = {(0, 0), (0, 1), (1, 0), (1, 1)}

    records = [
        {"x_index": 0, "y_index": 0, "status": "failed"},
        {"x_index": 0, "y_index": 1, "status": "success"},
        {"x_index": 1, "y_index": 0, "status": "failed"},
        {"x_index": 1, "y_index": 1, "status": "success"},
    ]

    for record in records:
        with metadata_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    result = select_failed_and_incomplete_cells(metadata_path, run_dir, expected_cells)

    assert result.failed_cells == [(0, 0), (1, 0)]
    assert result.incomplete_cells == [(0, 1), (1, 1)]


def test_select_missing_image_incomplete(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.jsonl"
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    expected_cells = {(0, 0), (0, 1), (1, 0)}

    records = [
        {
            "x_index": 0,
            "y_index": 0,
            "status": "success",
            "local_image_path": "images/0.png",
        },
        {
            "x_index": 0,
            "y_index": 1,
            "status": "success",
            "local_image_path": "images/1.png",
        },
        {
            "x_index": 1,
            "y_index": 0,
            "status": "skipped",
            "local_image_path": "images/2.png",
        },
    ]

    for record in records:
        with metadata_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    # Create only one image file
    (run_dir / "images").mkdir()
    (run_dir / "images" / "1.png").touch()

    result = select_failed_and_incomplete_cells(metadata_path, run_dir, expected_cells)

    assert result.failed_cells == []
    assert result.incomplete_cells == [(0, 0), (1, 0)]


def test_select_latest_wins(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.jsonl"
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    expected_cells = {(0, 0), (0, 1), (1, 0)}

    records = [
        {"x_index": 0, "y_index": 0, "status": "failed"},
        {"x_index": 0, "y_index": 0, "status": "success"},
        {"x_index": 0, "y_index": 1, "status": "success"},
        {"x_index": 0, "y_index": 1, "status": "failed"},
        {"x_index": 1, "y_index": 0, "status": "failed"},
        {"x_index": 1, "y_index": 0, "status": "success"},
        {"x_index": 1, "y_index": 0, "status": "failed"},
    ]

    for record in records:
        with metadata_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    result = select_failed_and_incomplete_cells(metadata_path, run_dir, expected_cells)

    assert result.failed_cells == [(0, 1), (1, 0)]
    assert result.incomplete_cells == [(0, 0)]


def test_select_stable_ordering(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.jsonl"
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    expected_cells = {(1, 1), (0, 0), (0, 1), (1, 0)}

    records = [
        {"x_index": 1, "y_index": 1, "status": "failed"},
        {"x_index": 0, "y_index": 1, "status": "failed"},
        {"x_index": 1, "y_index": 0, "status": "failed"},
        {"x_index": 0, "y_index": 0, "status": "failed"},
    ]

    for record in records:
        with metadata_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    result = select_failed_and_incomplete_cells(metadata_path, run_dir, expected_cells)

    assert result.failed_cells == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert result.incomplete_cells == []


def test_select_success_with_image(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.jsonl"
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    expected_cells = {(0, 0), (0, 1)}

    records = [
        {
            "x_index": 0,
            "y_index": 0,
            "status": "success",
            "local_image_path": "images/0.png",
        },
        {
            "x_index": 0,
            "y_index": 1,
            "status": "skipped",
            "local_image_path": "images/1.png",
        },
    ]

    for record in records:
        with metadata_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    (run_dir / "images").mkdir()
    (run_dir / "images" / "0.png").touch()
    (run_dir / "images" / "1.png").touch()

    result = select_failed_and_incomplete_cells(metadata_path, run_dir, expected_cells)

    assert result.failed_cells == []
    assert result.incomplete_cells == []


def test_load_latest_records_strict_malformed_json(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.jsonl"

    with metadata_path.open("w", encoding="utf-8") as f:
        f.write('{"x_index": 0, "y_index": 0}\n')
        f.write('{"malformed": invalid\n')
        f.write('{"x_index": 1, "y_index": 1}\n')

    with pytest.raises(ValueError, match="malformed JSON"):
        _load_latest_records_strict(metadata_path)


def test_load_latest_records_strict_non_dict_line(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.jsonl"

    metadata_path.write_text('["not", "a", "dict"]\n')

    with pytest.raises(ValueError, match="not a JSON object"):
        _load_latest_records_strict(metadata_path)


def test_load_latest_records_strict_missing_coordinates(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.jsonl"

    with metadata_path.open("w", encoding="utf-8") as f:
        f.write('{"x_index": 0}\n')
        f.write('{"y_index": 0}\n')
        f.write('{"x_index": 1, "y_index": 1}\n')

    records = _load_latest_records_strict(metadata_path)

    assert len(records) == 1
    assert (1, 1) in records


def test_image_exists_local_image_path(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "images").mkdir()
    (run_dir / "images" / "test.png").touch()

    record: dict[str, object] = {"local_image_path": "images/test.png"}

    assert _image_exists(record, run_dir) is True


def test_image_exists_missing_file(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    record: dict[str, object] = {"local_image_path": "images/test.png"}

    assert _image_exists(record, run_dir) is False


def test_image_exists_local_image_paths(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "images").mkdir()
    (run_dir / "images" / "test1.png").touch()
    (run_dir / "images" / "test2.png").touch()

    record: dict[str, object] = {
        "local_image_paths": ["images/test1.png", "images/test2.png"]
    }

    assert _image_exists(record, run_dir) is True


def test_image_exists_local_image_paths_one_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "images").mkdir()
    (run_dir / "images" / "test1.png").touch()

    record: dict[str, object] = {
        "local_image_paths": ["images/test1.png", "images/test2.png"]
    }

    assert _image_exists(record, run_dir) is False


def test_image_exists_no_path(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    record: dict[str, object] = {}

    assert _image_exists(record, run_dir) is False


def test_image_exists_absolute_path(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    images_dir = tmp_path / "external" / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "test.png").touch()

    record: dict[str, object] = {"local_image_path": str(images_dir / "test.png")}

    assert _image_exists(record, run_dir) is True


def test_select_skipped_without_image_incomplete(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.jsonl"
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    expected_cells = {(0, 0)}

    record = {
        "x_index": 0,
        "y_index": 0,
        "status": "skipped",
        "local_image_path": "images/0.png",
    }

    with metadata_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    result = select_failed_and_incomplete_cells(metadata_path, run_dir, expected_cells)

    assert result.failed_cells == []
    assert result.incomplete_cells == [(0, 0)]
