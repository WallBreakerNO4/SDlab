import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast


WorkflowNode = dict[str, object]
WorkflowDict = dict[str, WorkflowNode]

_LATENT_CLASS_TYPES = frozenset({"EmptyLatentImage", "EmptySD3LatentImage"})
_USER_PROMPT_SENTINEL = "{user_prompt}"
_CAPTION_SENTINEL = "{caption}"


@dataclass(slots=True)
class WorkflowOverrides:
    seed: int | None = None
    steps: int | None = None
    cfg: float | None = None
    denoise: float | None = None
    sampler_name: str | None = None
    scheduler: str | None = None
    width: int | None = None
    height: int | None = None
    batch_size: int | None = None


def load_workflow(workflow_path: str | Path) -> WorkflowDict:
    path = Path(workflow_path)
    with path.open("r", encoding="utf-8") as file:
        raw_data = cast(object, json.load(file))

    if not isinstance(raw_data, dict):
        raise ValueError("workflow json must be an object")

    workflow: WorkflowDict = {}
    raw_map = cast(dict[object, object], raw_data)
    for node_id_obj, node_obj in raw_map.items():
        if not isinstance(node_id_obj, str):
            raise ValueError("workflow node id must be string")
        if not isinstance(node_obj, dict):
            raise ValueError(f"workflow node {node_id_obj} must be an object")
        workflow[node_id_obj] = cast(WorkflowNode, node_obj)

    return workflow


def patch_workflow(
    workflow: WorkflowDict,
    positive_prompt: str,
    negative_prompt: str,
    overrides: WorkflowOverrides | None = None,
    ksampler_node_id: str | None = None,
    save_image_prefix: str | None = None,
    caption_prompt: str | None = None,
) -> WorkflowDict:
    patched = copy.deepcopy(workflow)
    active_overrides = overrides or WorkflowOverrides()

    selected_ksampler_id = _select_ksampler_node_id(patched, ksampler_node_id)
    ksampler_node = patched[selected_ksampler_id]

    positive_node_id = _extract_ref_node_id(ksampler_node, "positive")
    negative_node_id = _extract_ref_node_id(ksampler_node, "negative")
    latent_node_id = _extract_ref_node_id(ksampler_node, "latent_image")

    positive_node = _require_class_type(
        patched, positive_node_id, expected_class_type="CLIPTextEncode"
    )
    negative_node = _require_class_type(
        patched, negative_node_id, expected_class_type="CLIPTextEncode"
    )
    latent_node = _require_class_type(
        patched,
        latent_node_id,
        expected_class_type="EmptyLatentImage",
        allowed_types=_LATENT_CLASS_TYPES,
    )

    negative_inputs = _ensure_inputs(negative_node)
    negative_inputs["text"] = negative_prompt

    target_node_id, target_field = _resolve_positive_prompt_target(
        patched, positive_node
    )
    positive_target_inputs = _ensure_inputs(patched[target_node_id])
    positive_target_inputs[target_field] = positive_prompt

    if caption_prompt and caption_prompt.strip():
        caption_target = _resolve_optional_sentinel_target(
            patched, positive_node, _CAPTION_SENTINEL
        )
        if caption_target is not None:
            cap_node_id, cap_field = caption_target
            cap_inputs = _ensure_inputs(patched[cap_node_id])
            cap_inputs[cap_field] = caption_prompt

    _apply_if_provided(
        ksampler_node,
        {
            "seed": active_overrides.seed,
            "steps": active_overrides.steps,
            "cfg": active_overrides.cfg,
            "denoise": active_overrides.denoise,
            "sampler_name": active_overrides.sampler_name,
            "scheduler": active_overrides.scheduler,
        },
    )

    _apply_if_provided(
        latent_node,
        {
            "width": active_overrides.width,
            "height": active_overrides.height,
            "batch_size": active_overrides.batch_size,
        },
    )

    if save_image_prefix is not None:
        for node in patched.values():
            if node.get("class_type") != "SaveImage":
                continue
            save_inputs = _ensure_inputs(node)
            save_inputs["filename_prefix"] = save_image_prefix

    return patched


def _select_ksampler_node_id(
    workflow: WorkflowDict, ksampler_node_id: str | None
) -> str:
    candidates = [
        node_id
        for node_id, node in workflow.items()
        if node.get("class_type") == "KSampler"
    ]

    if not candidates:
        raise ValueError("no KSampler node found in workflow")

    if ksampler_node_id is not None:
        normalized_id = str(ksampler_node_id)
        if normalized_id not in workflow:
            raise ValueError(f"KSampler node id not found: {normalized_id}")
        if workflow[normalized_id].get("class_type") != "KSampler":
            actual = workflow[normalized_id].get("class_type")
            raise ValueError(
                f"node {normalized_id} is not KSampler (class_type={actual})"
            )
        return normalized_id

    if len(candidates) > 1:
        details = ", ".join(
            _format_node_title(workflow, node_id) for node_id in candidates
        )
        raise ValueError(
            f"multiple KSampler nodes found; please provide ksampler_node_id; candidates: {details}"
        )

    return candidates[0]


def _format_node_title(workflow: WorkflowDict, node_id: str) -> str:
    meta_obj = workflow[node_id].get("_meta")
    if isinstance(meta_obj, dict):
        meta = cast(dict[str, object], meta_obj)
        title_obj = meta.get("title")
        if isinstance(title_obj, str) and title_obj:
            return f"{node_id} ({title_obj})"
    return f"{node_id} (<no title>)"


def _extract_ref_node_id(node: WorkflowNode, input_name: str) -> str:
    inputs = _ensure_inputs(node)
    value_obj = inputs.get(input_name)
    if not isinstance(value_obj, list) or not value_obj:
        raise ValueError(f"invalid reference at inputs.{input_name}: {value_obj!r}")

    reference_node_id = cast(object, value_obj[0])
    if not isinstance(reference_node_id, str):
        node_id_type = type(reference_node_id).__name__
        raise ValueError(
            f"invalid reference node id type at inputs.{input_name}: {node_id_type}"
        )
    return reference_node_id


def _require_class_type(
    workflow: WorkflowDict,
    node_id: str,
    expected_class_type: str,
    allowed_types: frozenset[str] | None = None,
) -> WorkflowNode:
    if node_id not in workflow:
        raise ValueError(f"referenced node not found: {node_id}")
    node = workflow[node_id]
    actual = node.get("class_type")
    if allowed_types is not None:
        if actual not in allowed_types:
            raise ValueError(
                f"node {node_id} expected class_type in {{{', '.join(sorted(allowed_types))}}}, got {actual}"
            )
    elif actual != expected_class_type:
        raise ValueError(
            f"node {node_id} expected class_type={expected_class_type}, got {actual}"
        )
    return node


def _resolve_positive_prompt_target(
    workflow: WorkflowDict, positive_node: WorkflowNode
) -> tuple[str, str]:
    inputs = _ensure_inputs(positive_node)
    text_value = cast(object, inputs.get("text"))

    if isinstance(text_value, str):
        positive_node_id = _node_id_of(positive_node, workflow)
        return (positive_node_id, "text")

    if not isinstance(text_value, list) or not text_value:
        positive_node_id = _node_id_of(positive_node, workflow)
        raise ValueError(
            f"positive node {positive_node_id} inputs.text must be str or node reference, "
            f"got {type(text_value).__name__}"
        )

    target = _trace_sentinel_target(workflow, text_value, _USER_PROMPT_SENTINEL)
    if target is None:
        positive_node_id = _node_id_of(positive_node, workflow)
        raise ValueError(
            f"未能从 positive 节点 {positive_node_id} 回溯到 PrimitiveStringMultiline "
            f"且 find={_USER_PROMPT_SENTINEL!r} 的 replace 目标（深度上限已耗尽或链路断裂）"
        )
    return target


def _resolve_optional_sentinel_target(
    workflow: WorkflowDict,
    positive_node: WorkflowNode,
    sentinel: str,
) -> tuple[str, str] | None:
    """宽松语义回溯：沿正向 CLIPTextEncode 的 text 引用链查找指定 sentinel。

    与 _resolve_positive_prompt_target 的严格语义不同，找不到链路（text 为字符串、
    无引用、或链路中无匹配 sentinel）时返回 None 而非抛错，供 caption 等可选注入
    使用，以保持对不含该占位符链路的 workflow（如 common family）的向后兼容。
    """
    inputs = _ensure_inputs(positive_node)
    text_value = cast(object, inputs.get("text"))
    if not isinstance(text_value, list) or not text_value:
        return None
    return _trace_sentinel_target(workflow, text_value, sentinel)


def _node_id_of(node: WorkflowNode, workflow: WorkflowDict) -> str:
    for node_id, candidate in workflow.items():
        if candidate is node:
            return node_id
    raise ValueError("无法定位 positive 节点 ID")


def _trace_sentinel_target(
    workflow: WorkflowDict, start_ref: list[object], sentinel: str
) -> tuple[str, str] | None:
    visited: set[str] = set()

    def dfs(ref: list[object], depth: int) -> tuple[str, str] | None:
        if depth > 8:
            return None
        if not ref or not isinstance(ref[0], str):
            return None
        node_id = ref[0]
        if node_id in visited:
            return None
        visited.add(node_id)

        node = workflow.get(node_id)
        if not isinstance(node, dict):
            return None
        class_type = node.get("class_type")
        if class_type != "StringReplace":
            return None

        node_inputs_obj = node.get("inputs")
        if not isinstance(node_inputs_obj, dict):
            return None
        node_inputs = cast(dict[str, object], node_inputs_obj)

        find_value = cast(object, node_inputs.get("find"))
        if isinstance(find_value, str) and find_value == sentinel:
            replace_value = cast(object, node_inputs.get("replace"))
            if not isinstance(replace_value, list) or not replace_value:
                return None
            target_node_id_obj = replace_value[0]
            if not isinstance(target_node_id_obj, str):
                return None
            target_node = workflow.get(target_node_id_obj)
            if not isinstance(target_node, dict):
                return None
            if target_node.get("class_type") != "PrimitiveStringMultiline":
                return None
            return (target_node_id_obj, "value")

        for field_name in ("string", "replace"):
            value = cast(object, node_inputs.get(field_name))
            if isinstance(value, list) and value:
                found = dfs(value, depth + 1)
                if found is not None:
                    return found
        return None

    return dfs(start_ref, 0)


def _ensure_inputs(node: WorkflowNode) -> dict[str, object]:
    inputs_obj = node.get("inputs")
    if not isinstance(inputs_obj, dict):
        inputs_obj = {}
        node["inputs"] = inputs_obj
    return cast(dict[str, object], inputs_obj)


def _apply_if_provided(node: WorkflowNode, values: dict[str, object | None]) -> None:
    inputs = _ensure_inputs(node)
    for key, value in values.items():
        if value is None:
            continue
        inputs[key] = value
