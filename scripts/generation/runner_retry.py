from __future__ import annotations

import argparse
from typing import Callable

from scripts.generation.prompt_grid import Y_ARTIST_CHAIN, Y_POSITIVE_VALUE
from scripts.generation.run_replay import RunReplayConfig


def _apply_replay_config_to_args(
    args: argparse.Namespace,
    replay: RunReplayConfig,
) -> None:
    args.x_json = str(replay.x_json_path)
    args.y_json = str(replay.y_json_path)
    args.template = replay.template
    args.quality_prompt = replay.quality_prompt
    args.base_seed = replay.base_seed
    args.workflow_json = replay.workflow_api_path
    args.ksampler_node_id = replay.ksampler_node_id
    args.anima_artist_mixer = replay.anima_artist_mixer

    args.negative_prompt = replay.generation_overrides.negative_prompt
    args.append_negative_prompt = replay.generation_overrides.append_negative_prompt
    args.width = replay.generation_overrides.width
    args.height = replay.generation_overrides.height
    args.batch_size = replay.generation_overrides.batch_size
    args.steps = replay.generation_overrides.steps
    args.cfg = replay.generation_overrides.cfg
    args.denoise = replay.generation_overrides.denoise
    args.sampler_name = replay.generation_overrides.sampler_name
    args.scheduler = replay.generation_overrides.scheduler

    args.x_limit = None
    args.y_limit = None
    args.x_indexes = ",".join(str(i) for i in replay.selection.x_indexes)
    args.y_indexes = ",".join(str(i) for i in replay.selection.y_indexes)


def _parse_retry_error_codes(raw: str | None) -> set[str] | None:
    if raw is None:
        return None

    codes = [token.strip() for token in raw.split(",") if token.strip()]
    if not codes:
        raise ValueError("--retry-error-code 不能为空；可用逗号分隔多个错误码")
    return set(codes)


def _extract_retry_error_code(record: dict[str, object] | None) -> str | None:
    if record is None:
        return None

    error_obj = record.get("error")
    if not isinstance(error_obj, dict):
        return None

    code = error_obj.get("code")
    if isinstance(code, str):
        stripped = code.strip()
        if stripped:
            return stripped
    return None


def _filter_retry_failed_cells(
    *,
    failed_cells: list[tuple[int, int]],
    latest_records: dict[tuple[int, int], dict[str, object]],
    retry_error_codes: set[str] | None,
) -> list[tuple[int, int]]:
    if retry_error_codes is None:
        return failed_cells

    filtered: list[tuple[int, int]] = []
    for cell in failed_cells:
        code = _extract_retry_error_code(latest_records.get(cell))
        if code in retry_error_codes:
            filtered.append(cell)
    return filtered


def _build_retry_target_cells(
    *,
    retry_failed: bool,
    retry_incomplete: bool,
    failed_cells: list[tuple[int, int]],
    incomplete_cells: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    if retry_incomplete:
        return failed_cells + incomplete_cells
    if retry_failed:
        return failed_cells
    return []


def _record_workflow_hash(record: dict[str, object]) -> str | None:
    api_hash = record.get("workflow_api_sha256")
    if isinstance(api_hash, str) and api_hash:
        return api_hash
    return None


def _validate_retry_failed_cells_consistency(
    *,
    target_cells: list[tuple[int, int]],
    latest_records: dict[tuple[int, int], dict[str, object]],
    x_rows_by_index: dict[int, dict[str, str]],
    y_rows_by_index: dict[int, dict[str, str]],
    template: str,
    base_seed: int,
    workflow_hash: str,
    render_prompt: Callable[[str, dict[str, str], str], str],
    compute_prompt_hash: Callable[[str, str | None], str],
    derive_seed: Callable[[int, int, int], int],
    coerce_int_or_none: Callable[[object], int | None],
) -> None:
    for x_index, y_index in target_cells:
        record = latest_records.get((x_index, y_index))
        if record is None or record.get("status") != "failed":
            continue

        x_row = x_rows_by_index.get(x_index)
        y_row = y_rows_by_index.get(y_index)
        if x_row is None or y_row is None:
            raise ValueError(f"retry cell 不在回放选择范围内: x={x_index} y={y_index}")

        y_value = y_row.get("y", "")
        positive_y_value = y_row.get(Y_POSITIVE_VALUE, y_value)
        artist_chain_obj = y_row.get(Y_ARTIST_CHAIN)
        artist_chain = (
            artist_chain_obj if isinstance(artist_chain_obj, str) else None
        )
        expected_prompt = render_prompt(template, x_row, positive_y_value)
        expected_prompt_hash = compute_prompt_hash(expected_prompt, artist_chain)
        expected_seed = derive_seed(base_seed, x_index, y_index)

        if record.get("artist_chain") != artist_chain:
            raise ValueError(
                f"retry strict 校验失败(artist_chain): x={x_index} y={y_index}"
            )

        actual_prompt_hash = record.get("prompt_hash")
        if actual_prompt_hash != expected_prompt_hash:
            raise ValueError(
                f"retry strict 校验失败(prompt_hash): x={x_index} y={y_index} "
                f"expected={expected_prompt_hash} actual={actual_prompt_hash}"
            )

        actual_seed = coerce_int_or_none(record.get("seed"))
        if actual_seed != expected_seed:
            raise ValueError(
                f"retry strict 校验失败(seed): x={x_index} y={y_index} "
                f"expected={expected_seed} actual={record.get('seed')}"
            )

        actual_workflow_hash = _record_workflow_hash(record)
        if actual_workflow_hash != workflow_hash:
            raise ValueError(
                f"retry strict 校验失败(workflow_api_sha256): x={x_index} y={y_index} "
                f"expected={workflow_hash} actual={actual_workflow_hash}"
            )
