# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import argparse
from pathlib import Path

from .upload_contracts import _RUN_DIR_NAME_RE


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
    run_dirs.sort(key=lambda item: item.name, reverse=True)
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
    candidate = run_dir.name.strip()
    if _RUN_DIR_NAME_RE.fullmatch(candidate):
        return candidate

    run_json_dir = run_json.get("run_dir")
    if isinstance(run_json_dir, str):
        from_run_json = Path(run_json_dir).name.strip()
        if _RUN_DIR_NAME_RE.fullmatch(from_run_json):
            return from_run_json

    raise ValueError(f"run_dir 名称非法（需要 run-YYYYMMDDTHHMMSSZ）: {run_dir.name}")
