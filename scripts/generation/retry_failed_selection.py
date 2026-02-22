from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

if __package__ in {None, ""}:
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _coerce_int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _extract_local_image_path(existing: dict[str, object] | None) -> str | None:
    if existing is None:
        return None
    local_image_path = existing.get("local_image_path")
    if isinstance(local_image_path, str) and local_image_path.strip():
        return local_image_path
    return None


def _extract_local_image_paths(
    existing: dict[str, object] | None,
) -> list[str] | None:
    if existing is None:
        return None
    value = existing.get("local_image_paths")
    if not isinstance(value, list) or not value:
        return None
    paths: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            return None
        stripped = item.strip()
        if not stripped:
            continue
        paths.append(stripped)
    return paths if paths else None


@dataclass(slots=True)
class CellSelectionResult:
    """Result of selecting failed and incomplete cells."""

    failed_cells: list[tuple[int, int]]
    incomplete_cells: list[tuple[int, int]]


def select_failed_and_incomplete_cells(
    metadata_path: Path,
    run_dir: Path,
    expected_cells: set[tuple[int, int]],
) -> CellSelectionResult:
    """Select cells that need retry based on metadata.jsonl (latest-wins).

    Args:
        metadata_path: Path to metadata.jsonl
        run_dir: Run directory for resolving relative image paths
        expected_cells: Set of (x_index, y_index) tuples representing the full grid

    Returns:
        CellSelectionResult with sorted (stable) failed_cells and incomplete_cells

    Raises:
        ValueError: If metadata.jsonl contains malformed JSON lines
    """
    # Load latest records (latest-wins)
    latest_records: dict[tuple[int, int], dict[str, object]] = (
        _load_latest_records_strict(metadata_path)
    )

    failed_cells: list[tuple[int, int]] = []
    incomplete_cells: list[tuple[int, int]] = []

    for cell in sorted(expected_cells):  # Ensure stable ordering
        record = latest_records.get(cell)

        if record is None:
            # No record = incomplete
            incomplete_cells.append(cell)
            continue

        status = record.get("status")
        if status == "failed":
            # Failed = needs retry
            failed_cells.append(cell)
        elif status in {"success", "skipped"}:
            # Check if image exists
            if not _image_exists(record, run_dir):
                incomplete_cells.append(cell)
        else:
            # Unknown status or other = treat as incomplete
            incomplete_cells.append(cell)

    return CellSelectionResult(
        failed_cells=failed_cells,
        incomplete_cells=incomplete_cells,
    )


def _load_latest_records_strict(
    metadata_path: Path,
) -> dict[tuple[int, int], dict[str, object]]:
    """Load metadata.jsonl with latest-wins, raise on malformed JSON.

    Args:
        metadata_path: Path to metadata.jsonl

    Returns:
        Dict mapping (x_index, y_index) to latest record

    Raises:
        ValueError: If any line is malformed JSON
    """
    latest: dict[tuple[int, int], dict[str, object]] = {}
    if not metadata_path.exists():
        return latest

    with metadata_path.open("r", encoding="utf-8") as file:
        for line_num, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                payload = cast(object, json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"metadata.jsonl:{line_num}: malformed JSON: {exc}"
                ) from exc

            if not isinstance(payload, dict):
                raise ValueError(
                    f"metadata.jsonl:{line_num}: line is not a JSON object"
                )

            payload_dict: dict[str, object] = cast(dict[str, object], payload)
            x_index = _coerce_int_or_none(payload_dict.get("x_index"))
            y_index = _coerce_int_or_none(payload_dict.get("y_index"))
            if x_index is None or y_index is None:
                # Skip records without valid cell coordinates
                continue

            latest[(x_index, y_index)] = payload

    return latest


def _image_exists(record: dict[str, object], run_dir: Path) -> bool:
    """Check if image referenced by record exists on disk.

    Args:
        record: Metadata record with local_image_path or local_image_paths
        run_dir: Run directory for resolving relative paths

    Returns:
        True if image exists and is a file, False otherwise
    """
    local_image_paths = _extract_local_image_paths(record)
    if local_image_paths is not None:
        for local_image_path in local_image_paths:
            image_path = Path(local_image_path)
            if not image_path.is_absolute():
                image_path = run_dir / image_path
            if not (image_path.exists() and image_path.is_file()):
                return False
        return True

    local_image_path = _extract_local_image_path(record)
    if local_image_path is None:
        return False

    image_path = Path(local_image_path)
    if not image_path.is_absolute():
        image_path = run_dir / image_path
    return image_path.exists() and image_path.is_file()
