from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from scripts.generation.runner_selection import _extract_x_info_type
from scripts.generation.runner_workflow_context import _record_workflow_hash


def _build_base_metadata_record(
    *,
    status: str,
    x_index: int,
    y_index: int,
    x_row: dict[str, str],
    y_value: str,
    positive_prompt: str,
    prompt_hash: str,
    seed: int,
    generation_params: dict[str, object | None],
    workflow_hash: str,
    attempt: int,
) -> dict[str, object]:
    return {
        "status": status,
        "x_index": x_index,
        "y_index": y_index,
        "x_fields": {
            "gender": x_row.get("gender", ""),
            "characters": x_row.get("characters", ""),
            "series": x_row.get("series", ""),
            "rating": x_row.get("rating", ""),
            "general": x_row.get("general", ""),
        },
        "x_info_type": _extract_x_info_type(x_row),
        "y_value": y_value,
        "positive_prompt": positive_prompt,
        "prompt_hash": prompt_hash,
        "seed": seed,
        "attempt": attempt,
        "generation_params": generation_params,
        "workflow_api_sha256": workflow_hash,
        "comfyui_prompt_id": None,
        "remote_images": None,
        "local_image_path": None,
        "local_image_paths": None,
        "error": None,
    }


def _next_attempt(prev: dict[str, object] | None, *, increment: bool) -> int:
    if prev is None:
        return 1
    raw_attempt = _coerce_int_or_none(prev.get("attempt"))
    previous_attempt = raw_attempt if raw_attempt is not None and raw_attempt > 0 else 1
    if increment:
        return previous_attempt + 1
    return previous_attempt


def _should_resume_skip(
    existing: dict[str, object] | None,
    run_dir: Path,
    expected_prompt_hash: str,
    expected_seed: int,
    expected_workflow_hash: str,
) -> bool:
    if existing is None:
        return False
    if existing.get("status") not in {"success", "skipped"}:
        return False
    if existing.get("prompt_hash") != expected_prompt_hash:
        return False

    seed = _coerce_int_or_none(existing.get("seed"))
    if seed != expected_seed:
        return False

    if _record_workflow_hash(existing) != expected_workflow_hash:
        return False

    local_image_paths = _extract_local_image_paths(existing)
    if local_image_paths is not None:
        return all(_image_exists(run_dir, path) for path in local_image_paths)

    local_image_path = _extract_local_image_path(existing)
    if local_image_path is None:
        return False
    return _image_exists(run_dir, local_image_path)


def _extract_local_image_path(existing: dict[str, object] | None) -> str | None:
    if existing is None:
        return None
    local_image_path = existing.get("local_image_path")
    if isinstance(local_image_path, str) and local_image_path.strip():
        return local_image_path
    return None


def _extract_local_image_paths(existing: dict[str, object] | None) -> list[str] | None:
    if existing is None:
        return None
    value = existing.get("local_image_paths")
    if not isinstance(value, list) or not value:
        return None

    paths: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        stripped = item.strip()
        if stripped:
            paths.append(stripped)
    return paths if paths else None


def _effective_generation_params(
    args: argparse.Namespace,
    workflow_context: Any,
    x_row: dict[str, str],
    seed: int,
    *,
    final_negative_prompt_for_x_row: Callable[
        [argparse.Namespace, Any, dict[str, str]], str | None
    ],
) -> dict[str, object | None]:
    defaults = workflow_context.default_params if workflow_context is not None else {}

    def pick(key: str, override: object | None) -> object | None:
        if override is not None:
            return override
        return defaults.get(key)

    negative_prompt = final_negative_prompt_for_x_row(args, workflow_context, x_row)
    return {
        "seed": seed,
        "negative_prompt": negative_prompt,
        "width": pick("width", args.width),
        "height": pick("height", args.height),
        "batch_size": pick("batch_size", args.batch_size),
        "steps": pick("steps", args.steps),
        "cfg": pick("cfg", args.cfg),
        "denoise": pick("denoise", args.denoise),
        "sampler_name": pick("sampler_name", args.sampler_name),
        "scheduler": pick("scheduler", args.scheduler),
    }


def _effective_negative_prompt(
    args: argparse.Namespace, workflow_context: Any
) -> str | None:
    if args.negative_prompt is not None:
        return args.negative_prompt
    if workflow_context is None:
        return None
    return workflow_context.default_negative_prompt


def _final_negative_prompt_for_x_row(
    args: argparse.Namespace,
    workflow_context: Any,
    x_row: dict[str, str],
    *,
    append_negative_prompt: Callable[[str | None, str | None], str],
) -> str | None:
    base_negative_prompt = _effective_negative_prompt(args, workflow_context)
    if _extract_x_info_type(x_row) != "normal":
        return base_negative_prompt

    append_val = getattr(args, "append_negative_prompt", None)
    if base_negative_prompt is None and not append_val:
        return None

    return append_negative_prompt(
        base_negative_prompt,
        append_val,
    )


def _image_exists(run_dir: Path, local_image_path: str) -> bool:
    image_path = Path(local_image_path)
    if not image_path.is_absolute():
        image_path = run_dir / image_path
    return image_path.exists() and image_path.is_file()


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
