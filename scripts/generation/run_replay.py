from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar, cast


T = TypeVar("T")


@dataclass(slots=True)
class ReplayGenerationOverrides:
    negative_prompt: str | None
    append_negative_prompt: str | None
    width: int | None
    height: int | None
    batch_size: int | None
    steps: int | None
    cfg: float | None
    denoise: float | None
    sampler_name: str | None
    scheduler: str | None


@dataclass(slots=True)
class ReplaySelection:
    x_indexes: list[int]
    y_indexes: list[int]


@dataclass(slots=True)
class RunReplayConfig:
    x_json_path: Path
    y_json_path: Path
    template: str
    quality_prompt: str
    base_seed: int
    workflow_api_path: str | None
    generation_overrides: ReplayGenerationOverrides
    selection: ReplaySelection
    x_json_sha256: str
    y_json_sha256: str
    ksampler_node_id: str | None


def load_run_replay_config(
    run_dir: Path,
    *,
    strict_sha256: bool = True,
) -> RunReplayConfig:
    run_json_path = run_dir / "run.json"
    payload = _load_run_payload(run_json_path)

    x_json_path = Path(_require_str(payload, "x_json_path"))
    y_json_path = Path(_require_str(payload, "y_json_path"))
    template = _require_str(payload, "template")
    quality_prompt = _require_str(payload, "quality_prompt")
    base_seed = _require_int(payload, "base_seed")
    workflow_api_path = _require_optional_str(payload, "workflow_api_path")
    workflow_api_sha256 = _optional_top_level_str(payload, "workflow_api_sha256")
    x_json_sha256 = _require_str(payload, "x_json_sha256")
    y_json_sha256 = _require_str(payload, "y_json_sha256")
    ksampler_node_id = _parse_optional_ksampler_node_id(payload)

    generation_overrides = _parse_generation_overrides(
        _require_dict(payload, "generation_overrides")
    )
    selection = _parse_selection(_require_dict(payload, "selection"))

    if strict_sha256:
        _assert_sha256_matches(
            path=x_json_path,
            expected_sha256=x_json_sha256,
            field_name="x_json_sha256",
        )
        _assert_sha256_matches(
            path=y_json_path,
            expected_sha256=y_json_sha256,
            field_name="y_json_sha256",
        )
        _maybe_assert_workflow_sha256_matches(
            workflow_api_path=workflow_api_path,
            expected_sha256=workflow_api_sha256,
        )

    return RunReplayConfig(
        x_json_path=x_json_path,
        y_json_path=y_json_path,
        template=template,
        quality_prompt=quality_prompt,
        base_seed=base_seed,
        workflow_api_path=workflow_api_path,
        generation_overrides=generation_overrides,
        selection=selection,
        x_json_sha256=x_json_sha256,
        y_json_sha256=y_json_sha256,
        ksampler_node_id=ksampler_node_id,
    )


def _load_run_payload(run_json_path: Path) -> dict[str, object]:
    if not run_json_path.exists():
        raise ValueError(f"run.json 不存在: {run_json_path}")

    try:
        raw = run_json_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"run.json 读取失败: {run_json_path}") from exc

    try:
        payload = cast(object, json.loads(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"run.json 不是合法 JSON: {exc}") from exc

    return _as_object_dict(payload, field_name="run.json 顶层")


def _require_dict(record: dict[str, object], field_name: str) -> dict[str, object]:
    value = record.get(field_name)
    if value is None:
        raise ValueError(f"run.json 缺少字段: {field_name}")
    return _as_object_dict(value, field_name=field_name)


def _require_str(record: dict[str, object], field_name: str) -> str:
    value = record.get(field_name)
    if value is None:
        raise ValueError(f"run.json 缺少字段: {field_name}")
    if not isinstance(value, str):
        raise ValueError(f"run.json 字段类型错误: {field_name} 需为字符串")
    return value


def _require_optional_str(record: dict[str, object], field_name: str) -> str | None:
    if field_name not in record:
        raise ValueError(f"run.json 缺少字段: {field_name}")
    value = record.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"run.json 字段类型错误: {field_name} 需为字符串或 null")
    return value


def _require_int(record: dict[str, object], field_name: str) -> int:
    value = record.get(field_name)
    if value is None:
        raise ValueError(f"run.json 缺少字段: {field_name}")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"run.json 字段类型错误: {field_name} 需为整数")
    return value


def _optional_top_level_str(record: dict[str, object], field_name: str) -> str | None:
    if field_name not in record:
        return None
    value = record[field_name]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"run.json 字段类型错误: {field_name} 需为字符串或 null")
    return value


def _parse_generation_overrides(
    payload: dict[str, object],
) -> ReplayGenerationOverrides:
    return ReplayGenerationOverrides(
        negative_prompt=_require_optional_typed(payload, "negative_prompt", str),
        append_negative_prompt=_optional_typed(payload, "append_negative_prompt", str),
        width=_require_optional_int(payload, "width"),
        height=_require_optional_int(payload, "height"),
        batch_size=_require_optional_int(payload, "batch_size"),
        steps=_require_optional_int(payload, "steps"),
        cfg=_require_optional_float(payload, "cfg"),
        denoise=_require_optional_float(payload, "denoise"),
        sampler_name=_require_optional_typed(payload, "sampler_name", str),
        scheduler=_require_optional_typed(payload, "scheduler", str),
    )


def _parse_optional_ksampler_node_id(payload: dict[str, object]) -> str | None:
    config_snapshot_obj = payload.get("config_snapshot")
    if config_snapshot_obj is None:
        raise ValueError("run.json 缺少字段: config_snapshot")

    config_snapshot = _as_object_dict(
        config_snapshot_obj,
        field_name="config_snapshot",
    )

    workflow_obj = config_snapshot.get("workflow")
    if workflow_obj is None:
        raise ValueError("run.json 缺少字段: config_snapshot.workflow")

    workflow = _as_object_dict(
        workflow_obj,
        field_name="config_snapshot.workflow",
    )

    return _optional_typed(
        workflow,
        "ksampler_node_id",
        str,
        field_prefix="config_snapshot.workflow",
    )


def _parse_selection(payload: dict[str, object]) -> ReplaySelection:
    x_indexes = _require_int_list(payload, "selection.x_indexes", key="x_indexes")
    y_indexes = _require_int_list(payload, "selection.y_indexes", key="y_indexes")
    return ReplaySelection(x_indexes=x_indexes, y_indexes=y_indexes)


def _require_optional_typed(
    payload: dict[str, object],
    key: str,
    expected_type: type[T],
) -> T | None:
    if key not in payload:
        raise ValueError(f"run.json 缺少字段: generation_overrides.{key}")
    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, expected_type):
        type_name = expected_type.__name__
        raise ValueError(
            f"run.json 字段类型错误: generation_overrides.{key} 需为 {type_name} 或 null"
        )
    return value


def _optional_typed(
    payload: dict[str, object],
    key: str,
    expected_type: type[T],
    *,
    field_prefix: str = "generation_overrides",
) -> T | None:
    if key not in payload:
        return None
    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, expected_type):
        type_name = expected_type.__name__
        raise ValueError(
            f"run.json 字段类型错误: {field_prefix}.{key} 需为 {type_name} 或 null"
        )
    return value


def _require_optional_int(payload: dict[str, object], key: str) -> int | None:
    if key not in payload:
        raise ValueError(f"run.json 缺少字段: generation_overrides.{key}")
    value = payload[key]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"run.json 字段类型错误: generation_overrides.{key} 需为整数或 null"
        )
    return value


def _require_optional_float(payload: dict[str, object], key: str) -> float | None:
    if key not in payload:
        raise ValueError(f"run.json 缺少字段: generation_overrides.{key}")
    value = payload[key]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"run.json 字段类型错误: generation_overrides.{key} 需为数字或 null"
        )
    return float(value)


def _require_int_list(
    payload: dict[str, object],
    field_name: str,
    *,
    key: str,
) -> list[int]:
    if key not in payload:
        raise ValueError(f"run.json 缺少字段: {field_name}")
    value = payload[key]
    if not isinstance(value, list):
        raise ValueError(f"run.json 字段类型错误: {field_name} 需为整数列表")

    result: list[int] = []
    value_list: list[object] = [*value]
    for item_obj in value_list:
        if isinstance(item_obj, bool) or not isinstance(item_obj, int):
            raise ValueError(f"run.json 字段类型错误: {field_name} 需为整数列表")
        result.append(item_obj)
    return result


def _as_object_dict(value: object, *, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"run.json 字段类型错误: {field_name} 需为对象")

    result: dict[str, object] = {}
    raw_dict = cast(dict[object, object], value)
    for key_obj, item_obj in raw_dict.items():
        if not isinstance(key_obj, str):
            raise ValueError(f"run.json 字段类型错误: {field_name} 的键必须为字符串")
        result[key_obj] = item_obj
    return result


def _assert_sha256_matches(
    *,
    path: Path,
    expected_sha256: str,
    field_name: str,
) -> None:
    try:
        actual_sha256 = _sha256_file(path)
    except OSError as exc:
        raise ValueError(f"{field_name} 校验失败，无法读取文件: {path}") from exc

    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"{field_name} 校验失败: expected={expected_sha256}, actual={actual_sha256}"
        )


def _maybe_assert_workflow_sha256_matches(
    *,
    workflow_api_path: str | None,
    expected_sha256: str | None,
) -> None:
    if workflow_api_path is None or expected_sha256 is None:
        return

    workflow_path = Path(workflow_api_path)
    if not workflow_path.is_file():
        return

    try:
        actual_sha256 = _sha256_file(workflow_path)
    except OSError:
        return

    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"workflow_api_sha256 校验失败: expected={expected_sha256}, actual={actual_sha256}"
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()
