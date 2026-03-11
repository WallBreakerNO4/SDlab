from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from scripts.run_naming import validate_run_key


SCHEMA_VERSION = "image-run-config/v1"

_ROOT_KEYS = {
    "schema_version",
    "model",
    "prompts",
    "workflow",
    "generation",
    "selection",
}
_MODEL_KEYS = {"key", "name", "family", "links", "description"}
_MODEL_LINK_KEYS = {"homepage", "huggingface", "civitai"}
_MODEL_DESCRIPTION_KEYS = {"zh", "en"}
_PROMPTS_KEYS = {"x_path", "y_path"}
_WORKFLOW_KEYS = {"path", "ksampler_node_id"}
_GENERATION_KEYS = {
    "template",
    "base_seed",
    "negative_prompt",
    "append_negative_prompt",
    "width",
    "height",
    "batch_size",
    "steps",
    "cfg",
    "denoise",
    "sampler_name",
    "scheduler",
}
_SELECTION_KEYS = {"x_limit", "y_limit", "x_indexes", "y_indexes"}
_PROMPT_EXTENSIONS = {".yaml", ".yml", ".json"}
_WORKFLOW_EXTENSIONS = {".json"}


@dataclass(frozen=True)
class AssetRef:
    path: str
    repo_relative_path: str
    sha256: str


@dataclass(frozen=True)
class ModelConfig:
    key: str
    name: str
    family: str
    links: dict[str, str | None]
    description: dict[str, str]


@dataclass(frozen=True)
class PromptsConfig:
    x: AssetRef
    y: AssetRef


@dataclass(frozen=True)
class WorkflowConfig:
    path: str
    repo_relative_path: str
    sha256: str
    ksampler_node_id: str | None


@dataclass(frozen=True)
class GenerationConfig:
    template: str
    base_seed: int
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


@dataclass(frozen=True)
class SelectionConfig:
    x_limit: int | None
    y_limit: int | None
    x_indexes: list[int] | None
    y_indexes: list[int] | None


@dataclass(frozen=True)
class RunnerConfig:
    schema_version: str
    config_path: str
    config_sha256: str
    model: ModelConfig
    prompts: PromptsConfig
    workflow: WorkflowConfig
    generation: GenerationConfig
    selection: SelectionConfig


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"字段 {field_name} 必须是对象")
    return cast(Mapping[str, object], value)


def _validate_keys(
    payload: Mapping[str, object],
    *,
    field_name: str,
    allowed: set[str],
    required: set[str],
) -> None:
    unknown = sorted(key for key in payload if key not in allowed)
    if unknown:
        raise ValueError(f"字段 {field_name} 包含未知键: {', '.join(unknown)}")

    missing = sorted(key for key in required if key not in payload)
    if missing:
        raise ValueError(f"字段 {field_name} 缺少必填键: {', '.join(missing)}")


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"字段 {field_name} 必须是字符串")
    return value


def _require_non_empty_str(value: object, field_name: str) -> str:
    text = _require_str(value, field_name)
    if not text.strip():
        raise ValueError(f"字段 {field_name} 必须是非空字符串")
    return text


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"字段 {field_name} 必须是整数")
    return value


def _optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, field_name)


def _optional_float(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"字段 {field_name} 必须是数字或 null")
    return float(value)


def _optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, field_name)


def _optional_int_list(value: object, field_name: str) -> list[int] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"字段 {field_name} 必须是整数数组或 null")

    items: list[int] = []
    values = cast(list[object], value)
    for index, item in enumerate(values):
        items.append(_require_int(item, f"{field_name}[{index}]"))
    return items


def _resolve_repo_path(
    raw_path: object,
    *,
    field_name: str,
    repo_root: Path,
    allowed_extensions: set[str],
) -> AssetRef:
    relative_path = Path(_require_non_empty_str(raw_path, field_name))
    if relative_path.is_absolute():
        raise ValueError(f"字段 {field_name} 必须是 repo-relative 字符串路径")

    candidate = repo_root / relative_path
    resolved = candidate.resolve()

    if not resolved.is_relative_to(repo_root):
        raise ValueError(f"字段 {field_name} 必须是 repo-relative 路径: {resolved}")
    if not resolved.exists() or not resolved.is_file():
        raise ValueError(f"字段 {field_name} 指向的文件不存在: {resolved}")

    suffix = resolved.suffix.lower()
    if suffix not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise ValueError(f"字段 {field_name} 仅支持扩展名: {allowed}")

    return AssetRef(
        path=str(resolved),
        repo_relative_path=resolved.relative_to(repo_root).as_posix(),
        sha256=_sha256_file(resolved),
    )


def _load_model(payload: object) -> ModelConfig:
    mapping = _require_mapping(payload, "model")
    _validate_keys(
        mapping, field_name="model", allowed=_MODEL_KEYS, required=_MODEL_KEYS
    )

    links_payload = _require_mapping(mapping["links"], "model.links")
    _validate_keys(
        links_payload,
        field_name="model.links",
        allowed=_MODEL_LINK_KEYS,
        required=_MODEL_LINK_KEYS,
    )
    links = {
        key: _optional_str(links_payload[key], f"model.links.{key}")
        for key in sorted(_MODEL_LINK_KEYS)
    }

    description_payload = _require_mapping(mapping["description"], "model.description")
    _validate_keys(
        description_payload,
        field_name="model.description",
        allowed=_MODEL_DESCRIPTION_KEYS,
        required=_MODEL_DESCRIPTION_KEYS,
    )
    description = {
        key: _require_str(description_payload[key], f"model.description.{key}")
        for key in sorted(_MODEL_DESCRIPTION_KEYS)
    }

    return ModelConfig(
        key=validate_run_key(
            _require_non_empty_str(mapping["key"], "model.key"),
            field_name="model.key",
        ),
        name=_require_non_empty_str(mapping["name"], "model.name"),
        family=_require_non_empty_str(mapping["family"], "model.family"),
        links=links,
        description=description,
    )


def _load_prompts(payload: object, *, repo_root: Path) -> PromptsConfig:
    mapping = _require_mapping(payload, "prompts")
    _validate_keys(
        mapping, field_name="prompts", allowed=_PROMPTS_KEYS, required=_PROMPTS_KEYS
    )

    return PromptsConfig(
        x=_resolve_repo_path(
            mapping["x_path"],
            field_name="prompts.x_path",
            repo_root=repo_root,
            allowed_extensions=_PROMPT_EXTENSIONS,
        ),
        y=_resolve_repo_path(
            mapping["y_path"],
            field_name="prompts.y_path",
            repo_root=repo_root,
            allowed_extensions=_PROMPT_EXTENSIONS,
        ),
    )


def _load_workflow(payload: object, *, repo_root: Path) -> WorkflowConfig:
    mapping = _require_mapping(payload, "workflow")
    _validate_keys(
        mapping, field_name="workflow", allowed=_WORKFLOW_KEYS, required=_WORKFLOW_KEYS
    )

    asset = _resolve_repo_path(
        mapping["path"],
        field_name="workflow.path",
        repo_root=repo_root,
        allowed_extensions=_WORKFLOW_EXTENSIONS,
    )
    return WorkflowConfig(
        path=asset.path,
        repo_relative_path=asset.repo_relative_path,
        sha256=asset.sha256,
        ksampler_node_id=_optional_str(
            mapping["ksampler_node_id"], "workflow.ksampler_node_id"
        ),
    )


def _load_generation(payload: object) -> GenerationConfig:
    mapping = _require_mapping(payload, "generation")
    _validate_keys(
        mapping,
        field_name="generation",
        allowed=_GENERATION_KEYS,
        required=_GENERATION_KEYS,
    )

    return GenerationConfig(
        template=_require_str(mapping["template"], "generation.template"),
        base_seed=_require_int(mapping["base_seed"], "generation.base_seed"),
        negative_prompt=_optional_str(
            mapping["negative_prompt"], "generation.negative_prompt"
        ),
        append_negative_prompt=_optional_str(
            mapping["append_negative_prompt"], "generation.append_negative_prompt"
        ),
        width=_optional_int(mapping["width"], "generation.width"),
        height=_optional_int(mapping["height"], "generation.height"),
        batch_size=_optional_int(mapping["batch_size"], "generation.batch_size"),
        steps=_optional_int(mapping["steps"], "generation.steps"),
        cfg=_optional_float(mapping["cfg"], "generation.cfg"),
        denoise=_optional_float(mapping["denoise"], "generation.denoise"),
        sampler_name=_optional_str(mapping["sampler_name"], "generation.sampler_name"),
        scheduler=_optional_str(mapping["scheduler"], "generation.scheduler"),
    )


def _load_selection(payload: object) -> SelectionConfig:
    mapping = _require_mapping(payload, "selection")
    _validate_keys(
        mapping,
        field_name="selection",
        allowed=_SELECTION_KEYS,
        required=_SELECTION_KEYS,
    )

    return SelectionConfig(
        x_limit=_optional_int(mapping["x_limit"], "selection.x_limit"),
        y_limit=_optional_int(mapping["y_limit"], "selection.y_limit"),
        x_indexes=_optional_int_list(mapping["x_indexes"], "selection.x_indexes"),
        y_indexes=_optional_int_list(mapping["y_indexes"], "selection.y_indexes"),
    )


def load_runner_config(config_path: str, *, repo_root: Path) -> RunnerConfig:
    repo_root = repo_root.resolve()
    config_file = Path(config_path).resolve()

    if not config_file.is_relative_to(repo_root):
        raise ValueError(f"字段 config_path 必须是 repo-relative 路径: {config_file}")
    if not config_file.exists() or not config_file.is_file():
        raise ValueError(f"字段 config_path 指向的文件不存在: {config_file}")

    payload_obj = cast(object, yaml.safe_load(config_file.read_text(encoding="utf-8")))
    mapping = _require_mapping(payload_obj, "<root>")
    _validate_keys(
        mapping, field_name="<root>", allowed=_ROOT_KEYS, required=_ROOT_KEYS
    )

    schema_version = _require_str(mapping["schema_version"], "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"字段 schema_version 必须为 {SCHEMA_VERSION}: {schema_version}"
        )

    return RunnerConfig(
        schema_version=schema_version,
        config_path=config_file.relative_to(repo_root).as_posix(),
        config_sha256=_sha256_file(config_file),
        model=_load_model(mapping["model"]),
        prompts=_load_prompts(mapping["prompts"], repo_root=repo_root),
        workflow=_load_workflow(mapping["workflow"], repo_root=repo_root),
        generation=_load_generation(mapping["generation"]),
        selection=_load_selection(mapping["selection"]),
    )


__all__ = ["RunnerConfig", "load_runner_config"]
