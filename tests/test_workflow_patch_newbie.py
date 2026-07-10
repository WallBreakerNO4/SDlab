# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generation.workflow_patch import (
    _LATENT_CLASS_TYPES,
    WorkflowDict,
    WorkflowOverrides,
    load_workflow,
    patch_workflow,
)
from scripts.generation.runner_workflow_context import (
    _extract_workflow_defaults,
    _load_workflow_context,
)


NEWBIE_WORKFLOW = ROOT / "data" / "models" / "newbie-image-exp0.1" / "api.json"


def _inputs(node: dict[str, object]) -> dict[str, object]:
    inputs_obj = node.get("inputs")
    assert isinstance(inputs_obj, dict)
    return cast(dict[str, object], inputs_obj)


# --------------------------------------------------------------------------- #
# 1. patch_workflow 正向 prompt 直接写入 CLIPTextEncode 41:53
# --------------------------------------------------------------------------- #
def test_patch_workflow_newbie_positive_writes_directly_to_clip_text_encode():
    workflow = load_workflow(NEWBIE_WORKFLOW)

    patched = patch_workflow(
        workflow,
        positive_prompt="complete positive prompt string",
        negative_prompt="negative text",
    )

    assert _inputs(patched["41:53"]).get("text") == "complete positive prompt string"


# --------------------------------------------------------------------------- #
# 2. 负向 prompt 直接写入 CLIPTextEncode 41:54
# --------------------------------------------------------------------------- #
def test_patch_workflow_newbie_negative_writes_directly_to_clip_text_encode():
    workflow = load_workflow(NEWBIE_WORKFLOW)

    patched = patch_workflow(
        workflow,
        positive_prompt="positive prompt",
        negative_prompt="plain negative prompt",
    )

    assert _inputs(patched["41:54"]).get("text") == "plain negative prompt"


# --------------------------------------------------------------------------- #
# 3. EmptySD3LatentImage 的 width/height/batch_size 覆盖
# --------------------------------------------------------------------------- #
def test_patch_workflow_newbie_overrides_empty_sd3_latent_fields():
    workflow = load_workflow(NEWBIE_WORKFLOW)

    patched = patch_workflow(
        workflow,
        positive_prompt="positive prompt",
        negative_prompt="neg",
        overrides=WorkflowOverrides(width=768, height=1024, batch_size=2),
    )

    latent_inputs = _inputs(patched["41:31"])
    assert latent_inputs.get("width") == 768
    assert latent_inputs.get("height") == 1024
    assert latent_inputs.get("batch_size") == 2
    assert patched["41:31"].get("class_type") == "EmptySD3LatentImage"


# --------------------------------------------------------------------------- #
# 4. KSampler 41:3 的 steps / cfg / sampler / scheduler / seed 覆盖
# --------------------------------------------------------------------------- #
def test_patch_workflow_newbie_overrides_ksampler_fields():
    workflow = load_workflow(NEWBIE_WORKFLOW)

    patched = patch_workflow(
        workflow,
        positive_prompt="positive prompt",
        negative_prompt="neg",
        overrides=WorkflowOverrides(
            seed=42,
            steps=30,
            cfg=4.5,
            denoise=0.75,
            sampler_name="euler",
            scheduler="normal",
        ),
    )

    ksampler_inputs = _inputs(patched["41:3"])
    assert ksampler_inputs.get("seed") == 42
    assert ksampler_inputs.get("steps") == 30
    assert ksampler_inputs.get("cfg") == 4.5
    assert ksampler_inputs.get("denoise") == 0.75
    assert ksampler_inputs.get("sampler_name") == "euler"
    assert ksampler_inputs.get("scheduler") == "normal"


# --------------------------------------------------------------------------- #
# 5. _LATENT_CLASS_TYPES 常量包含两个 latent 类型
# --------------------------------------------------------------------------- #
def test_latent_class_types_includes_both_empty_latent_classes():
    assert "EmptyLatentImage" in _LATENT_CLASS_TYPES
    assert "EmptySD3LatentImage" in _LATENT_CLASS_TYPES


# --------------------------------------------------------------------------- #
# 6. _load_workflow_context 不抛错 + _extract_workflow_defaults 默认值
# --------------------------------------------------------------------------- #
class _Namespace:
    def __init__(self, **kwargs: object) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_load_workflow_context_succeeds_on_newbie_api_json():
    args = _Namespace(
        dry_run=False,
        workflow_json=str(NEWBIE_WORKFLOW),
        ksampler_node_id="41:3",
    )

    context = _load_workflow_context(args)

    assert context is not None
    assert context.selected_ksampler_id == "41:3"


def test_extract_workflow_defaults_returns_newbie_default_params():
    workflow = load_workflow(NEWBIE_WORKFLOW)

    defaults = _extract_workflow_defaults(workflow, "41:3")

    assert defaults["width"] == 1024
    assert defaults["height"] == 1536
    assert defaults["batch_size"] == 1
    assert defaults["steps"] == 20
    assert defaults["cfg"] == 5.5
    assert defaults["denoise"] == 1.0
