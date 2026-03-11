from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from scripts.generation.runner_env import _env_str
from scripts.run_naming import validate_run_key

DEFAULT_RUN_ROOT = "comfyui_api_outputs"


@dataclass(slots=True)
class RunArtifacts:
    run_dir: Path
    images_dir: Path
    run_json_path: Path
    metadata_path: Path


def _prepare_run_artifacts(
    run_dir_arg: str | None, *, default_run_key: str
) -> RunArtifacts:
    if run_dir_arg:
        run_dir = Path(run_dir_arg)
    else:
        run_root = Path(_env_str("COMFYUI_OUT_DIR") or DEFAULT_RUN_ROOT)
        run_key = validate_run_key(default_run_key, field_name="model.key")
        run_dir = run_root / run_key

    _ = validate_run_key(run_dir.name, field_name="run_dir")

    run_dir.mkdir(parents=True, exist_ok=True)
    return RunArtifacts(
        run_dir=run_dir,
        images_dir=run_dir / "images",
        run_json_path=run_dir / "run.json",
        metadata_path=run_dir / "metadata.jsonl",
    )


def _prepare_existing_run_artifacts(run_dir_arg: str | None) -> RunArtifacts:
    if not run_dir_arg:
        raise ValueError("retry 模式必须提供 --run-dir")

    run_dir = Path(run_dir_arg)
    if not run_dir.exists() or not run_dir.is_dir():
        raise ValueError(f"retry 模式 --run-dir 不存在或不是目录: {run_dir}")
    _ = validate_run_key(run_dir.name, field_name="run_dir")

    return RunArtifacts(
        run_dir=run_dir,
        images_dir=run_dir / "images",
        run_json_path=run_dir / "run.json",
        metadata_path=run_dir / "metadata.jsonl",
    )


class _MetadataWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.file = None

    def __enter__(self) -> "_MetadataWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_newline_terminated(self.path)
        self.file = self.path.open("a", encoding="utf-8")
        return self

    def append(self, record: dict[str, object]) -> None:
        if self.file is None:
            raise RuntimeError("metadata writer is closed")
        line = json.dumps(record, ensure_ascii=False)
        self.file.write(line)
        self.file.write("\n")
        self.file.flush()
        os.fsync(self.file.fileno())

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.file is not None:
            self.file.close()
            self.file = None


def _metadata_writer(path: Path) -> _MetadataWriter:
    return _MetadataWriter(path)


def _ensure_newline_terminated(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return

    with path.open("rb+") as file:
        file.seek(-1, os.SEEK_END)
        last_byte = file.read(1)
        if last_byte == b"\n":
            return
        file.seek(0, os.SEEK_END)
        file.write(b"\n")
        file.flush()
        os.fsync(file.fileno())


def _load_latest_metadata_records(
    metadata_path: Path,
) -> dict[tuple[int, int], dict[str, object]]:
    latest: dict[tuple[int, int], dict[str, object]] = {}
    if not metadata_path.exists():
        return latest

    with metadata_path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue

            x_index = _coerce_int_or_none(payload.get("x_index"))
            y_index = _coerce_int_or_none(payload.get("y_index"))
            if x_index is None or y_index is None:
                continue

            latest[(x_index, y_index)] = payload

    return latest


def _load_latest_metadata_records_strict(
    metadata_path: Path,
) -> dict[tuple[int, int], dict[str, object]]:
    latest: dict[tuple[int, int], dict[str, object]] = {}
    if not metadata_path.exists():
        return latest

    with metadata_path.open("r", encoding="utf-8") as file:
        for line_num, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"metadata.jsonl:{line_num}: malformed JSON: {exc}"
                ) from exc

            if not isinstance(payload, dict):
                raise ValueError(
                    f"metadata.jsonl:{line_num}: line is not a JSON object"
                )

            x_index = _coerce_int_or_none(payload.get("x_index"))
            y_index = _coerce_int_or_none(payload.get("y_index"))
            if x_index is None or y_index is None:
                continue

            latest[(x_index, y_index)] = payload

    return latest


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
