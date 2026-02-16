import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast


WorkflowNode = dict[str, object]
WorkflowDict = dict[str, WorkflowNode]


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
        patched, latent_node_id, expected_class_type="EmptyLatentImage"
    )

    positive_inputs = _ensure_inputs(positive_node)
    negative_inputs = _ensure_inputs(negative_node)

    positive_inputs["text"] = positive_prompt
    negative_inputs["text"] = negative_prompt

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
    workflow: WorkflowDict, node_id: str, expected_class_type: str
) -> WorkflowNode:
    if node_id not in workflow:
        raise ValueError(f"referenced node not found: {node_id}")
    node = workflow[node_id]
    actual = node.get("class_type")
    if actual != expected_class_type:
        raise ValueError(
            f"node {node_id} expected class_type={expected_class_type}, got {actual}"
        )
    return node


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
