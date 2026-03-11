# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.run_naming import validate_run_dir_path, validate_run_key


def _is_valid_run_dir(run_dir: Path) -> bool:
    return (
        run_dir.is_dir()
        and (run_dir / "run.json").is_file()
        and (run_dir / "metadata.jsonl").is_file()
        and (run_dir / "images").is_dir()
    )


def _discover_run_dirs(run_root: Path) -> list[Path]:
    if not run_root.exists() or not run_root.is_dir():
        raise FileNotFoundError(f"run_root 不存在或不是目录: {run_root}")

    run_dirs = [
        child.resolve()
        for child in run_root.iterdir()
        if child.is_dir() and _is_valid_run_dir(child)
    ]
    run_dirs.sort(key=lambda item: (item.stat().st_mtime_ns, item.name), reverse=True)
    return run_dirs


def _resolve_single_run_dir(run_root: Path, run_dir_arg: str) -> Path:
    user_path = Path(run_dir_arg)
    if user_path.exists():
        candidate = user_path.resolve()
    else:
        candidate = (run_root / run_dir_arg).resolve()

    if not _is_valid_run_dir(candidate):
        raise FileNotFoundError(
            f"run_dir 必须包含 run.json / metadata.jsonl / images: {candidate}"
        )
    return candidate


def _resolve_selected_run_dirs(args: argparse.Namespace) -> list[Path]:
    run_root = Path(str(args.run_root)).resolve()

    run_dir_arg = getattr(args, "run_dir", None)
    if isinstance(run_dir_arg, str) and run_dir_arg.strip():
        return [_resolve_single_run_dir(run_root, run_dir_arg.strip())]

    if bool(getattr(args, "all_runs", False)):
        return _discover_run_dirs(run_root)

    discovered = _discover_run_dirs(run_root)
    if not discovered:
        raise FileNotFoundError(f"未在 run_root 下发现可用 run: {run_root}")
    return [discovered[0]]


def _resolve_run_dir_name(run_dir: Path, run_json: dict[str, object]) -> str:
    candidate = validate_run_dir_path(run_dir)

    run_json_dir = run_json.get("run_dir")
    if isinstance(run_json_dir, str):
        from_run_json = validate_run_key(
            run_json_dir,
            field_name="run_json.run_dir",
        )
        if from_run_json != candidate:
            raise ValueError("run.json 中 run_dir 与目录名不一致")

    run_json_key = run_json.get("run_key")
    if isinstance(run_json_key, str):
        normalized_run_key = validate_run_key(
            run_json_key,
            field_name="run_json.run_key",
        )
        if normalized_run_key != candidate:
            raise ValueError("run.json 中 run_key 与目录名不一致")

    return candidate
