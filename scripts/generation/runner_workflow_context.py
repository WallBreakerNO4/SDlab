from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from scripts.generation.runner_payload import _sha256_file
from scripts.generation.workflow_patch import (
    WorkflowDict,
    WorkflowOverrides,
    load_workflow,
    patch_workflow,
)


@dataclass(slots=True)
class WorkflowContext:
    workflow: WorkflowDict
    workflow_json_path: str
    workflow_hash: str
    selected_ksampler_id: str
    default_negative_prompt: str
    default_params: dict[str, object | None]


def _load_workflow_context(args: argparse.Namespace) -> WorkflowContext | None:
    if args.dry_run:
        return None

    workflow_json_path = args.workflow_json
    if not workflow_json_path:
        raise ValueError("非 dry-run 模式缺少 workflow 路径")

    workflow_path = Path(workflow_json_path)
    if not workflow_path.exists() or not workflow_path.is_file():
        raise ValueError(f"workflow 文件不存在: {workflow_json_path}")

    workflow = load_workflow(workflow_path)
    workflow_hash = _sha256_file(workflow_path)
    selected_ksampler_id = _resolve_ksampler_id(workflow, args.ksampler_node_id)

    defaults = _extract_workflow_defaults(workflow, selected_ksampler_id)
    default_negative_prompt_obj = defaults.get("negative_prompt")
    default_negative_prompt = (
        default_negative_prompt_obj
        if isinstance(default_negative_prompt_obj, str)
        else ""
    )

    try:
        _ = patch_workflow(
            workflow,
            positive_prompt="__workflow_validation_positive__",
            negative_prompt=default_negative_prompt,
            overrides=WorkflowOverrides(seed=0),
            ksampler_node_id=selected_ksampler_id,
        )
    except Exception as exc:
        raise ValueError(
            "workflow 结构不符合 CLIPTextEncode 注入要求，请使用 CLIPTextEncode 版 workflow"
        ) from exc

    return WorkflowContext(
        workflow=workflow,
        workflow_json_path=str(workflow_path),
        workflow_hash=workflow_hash,
        selected_ksampler_id=selected_ksampler_id,
        default_negative_prompt=default_negative_prompt,
        default_params=defaults,
    )


def _resolve_ksampler_id(workflow: WorkflowDict, requested: str | None) -> str:
    candidates = [
        node_id
        for node_id, node in workflow.items()
        if isinstance(node, dict) and node.get("class_type") == "KSampler"
    ]
    if not candidates:
        raise ValueError("workflow 中未找到 KSampler")

    if requested is not None:
        node_id = str(requested)
        if node_id not in workflow:
            raise ValueError(f"KSampler 节点不存在: {node_id}")
        node = workflow[node_id]
        if node.get("class_type") != "KSampler":
            class_type = node.get("class_type")
            raise ValueError(f"节点 {node_id} 不是 KSampler (class_type={class_type})")
        return node_id

    if len(candidates) > 1:
        details = ", ".join(
            _format_node_title(workflow, node_id) for node_id in candidates
        )
        raise ValueError(
            f"workflow 中存在多个 KSampler；请传入 --ksampler-node-id；可选: {details}"
        )

    return candidates[0]


def _format_node_title(workflow: WorkflowDict, node_id: str) -> str:
    node = workflow.get(node_id, {})
    meta_obj = node.get("_meta") if isinstance(node, dict) else None
    if isinstance(meta_obj, dict):
        title_obj = meta_obj.get("title")
        if isinstance(title_obj, str) and title_obj:
            return f"{node_id} ({title_obj})"
    return f"{node_id} (<no title>)"


def _extract_workflow_defaults(
    workflow: WorkflowDict,
    ksampler_id: str,
) -> dict[str, object | None]:
    node = workflow.get(ksampler_id)
    if not isinstance(node, dict):
        raise ValueError(f"KSampler 节点无效: {ksampler_id}")
    node_inputs = _as_dict(node.get("inputs"))

    negative_node_id = _extract_ref_node_id(node_inputs.get("negative"), "negative")
    latent_node_id = _extract_ref_node_id(
        node_inputs.get("latent_image"), "latent_image"
    )

    negative_node = _as_dict(workflow.get(negative_node_id))
    if negative_node.get("class_type") != "CLIPTextEncode":
        class_type = negative_node.get("class_type")
        raise ValueError(f"负向节点必须是 CLIPTextEncode，当前为: {class_type}")
    negative_inputs = _as_dict(negative_node.get("inputs"))
    negative_prompt_obj = negative_inputs.get("text")
    negative_prompt = (
        negative_prompt_obj if isinstance(negative_prompt_obj, str) else None
    )

    latent_node = _as_dict(workflow.get(latent_node_id))
    if latent_node.get("class_type") != "EmptyLatentImage":
        class_type = latent_node.get("class_type")
        raise ValueError(f"latent 节点必须是 EmptyLatentImage，当前为: {class_type}")
    latent_inputs = _as_dict(latent_node.get("inputs"))

    return {
        "negative_prompt": negative_prompt,
        "width": _coerce_int_or_none(latent_inputs.get("width")),
        "height": _coerce_int_or_none(latent_inputs.get("height")),
        "batch_size": _coerce_int_or_none(latent_inputs.get("batch_size")),
        "steps": _coerce_int_or_none(node_inputs.get("steps")),
        "cfg": _coerce_float_or_none(node_inputs.get("cfg")),
        "denoise": _coerce_float_or_none(node_inputs.get("denoise")),
        "sampler_name": _coerce_str_or_none(node_inputs.get("sampler_name")),
        "scheduler": _coerce_str_or_none(node_inputs.get("scheduler")),
    }


def _extract_ref_node_id(value: object, input_name: str) -> str:
    if not isinstance(value, list) or not value:
        raise ValueError(f"workflow 引用字段无效: inputs.{input_name}")
    first = value[0]
    if not isinstance(first, str) or not first:
        raise ValueError(f"workflow 引用节点 ID 无效: inputs.{input_name}")
    return first


def _record_workflow_hash(record: dict[str, object]) -> str | None:
    api_hash = record.get("workflow_api_sha256")
    if isinstance(api_hash, str) and api_hash:
        return api_hash
    return None


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


def _coerce_float_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _coerce_str_or_none(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None


def _as_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    raise ValueError("workflow 结构不符合预期，请使用 CLIPTextEncode 版 workflow")
