# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import sys
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generation.workflow_patch import (
    _CAPTION_SENTINEL,
    _LATENT_CLASS_TYPES,
    _resolve_optional_sentinel_target,
    _resolve_positive_prompt_target,
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

XML_PROMPT = (
    "<character_1>\n<n>$character_1$</n>\n<gender>1girl</gender>\n</character_1>"
)


def _inputs(node: dict[str, object]) -> dict[str, object]:
    inputs_obj = node.get("inputs")
    assert isinstance(inputs_obj, dict)
    return cast(dict[str, object], inputs_obj)


# --------------------------------------------------------------------------- #
# 1. patch_workflow 正向回溯：注入 XML 到节点 48，引用链不被破坏
# --------------------------------------------------------------------------- #
def test_patch_workflow_newbie_positive_backtrace_injects_xml_on_node_48():
    workflow = load_workflow(NEWBIE_WORKFLOW)

    patched = patch_workflow(
        workflow,
        positive_prompt=XML_PROMPT,
        negative_prompt="negative text",
    )

    # 正向 prompt 经回溯后落到节点 48 (PrimitiveStringMultiline "User Prompt")
    assert _inputs(patched["48"]).get("value") == XML_PROMPT

    # 引用链保持完整：CLIPTextEncode 41:53.text 仍是节点引用 ["46", 0]
    positive_text = _inputs(patched["41:53"]).get("text")
    assert positive_text == ["46", 0]


# --------------------------------------------------------------------------- #
# 2. 负向 prompt 直接写入 CLIPTextEncode 41:54
# --------------------------------------------------------------------------- #
def test_patch_workflow_newbie_negative_writes_directly_to_clip_text_encode():
    workflow = load_workflow(NEWBIE_WORKFLOW)

    patched = patch_workflow(
        workflow,
        positive_prompt=XML_PROMPT,
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
        positive_prompt=XML_PROMPT,
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
        positive_prompt=XML_PROMPT,
        negative_prompt="neg",
        overrides=WorkflowOverrides(
            seed=42,
            steps=30,
            cfg=4.5,
            sampler_name="euler",
            scheduler="normal",
        ),
    )

    ksampler_inputs = _inputs(patched["41:3"])
    assert ksampler_inputs.get("seed") == 42
    assert ksampler_inputs.get("steps") == 30
    assert ksampler_inputs.get("cfg") == 4.5
    assert ksampler_inputs.get("sampler_name") == "euler"
    assert ksampler_inputs.get("scheduler") == "normal"


# --------------------------------------------------------------------------- #
# 5. 回溯算法 sentinel mini-workflow：命中 + 失败路径
# --------------------------------------------------------------------------- #
def _string_replace_node(
    string_ref: list[object],
    find: str,
    replace_ref: list[object],
) -> dict[str, object]:
    return {
        "class_type": "StringReplace",
        "inputs": {"string": string_ref, "find": find, "replace": replace_ref},
    }


def _primitive_multiline(value: str) -> dict[str, object]:
    return {
        "class_type": "PrimitiveStringMultiline",
        "inputs": {"value": value},
    }


def test_resolve_positive_prompt_target_finds_user_prompt_sentinel():
    workflow: WorkflowDict = {
        "pos": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": ["sr_outer", 0]},
        },
        "sr_outer": _string_replace_node(["sr_inner", 0], "{caption}", ["cap", 0]),
        "sr_inner": _string_replace_node(
            ["tpl", 0], "{user_prompt}", ["up", 0]
        ),
        "cap": _primitive_multiline("caption text"),
        "tpl": _primitive_multiline("template text"),
        "up": _primitive_multiline("user prompt original"),
    }

    target_id, target_field = _resolve_positive_prompt_target(
        workflow, workflow["pos"]
    )

    assert target_id == "up"
    assert target_field == "value"


def test_resolve_positive_prompt_target_raises_when_sentinel_missing():
    workflow: WorkflowDict = {
        "pos": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": ["sr_outer", 0]},
        },
        "sr_outer": _string_replace_node(["sr_inner", 0], "{caption}", ["cap", 0]),
        "sr_inner": _string_replace_node(["tpl", 0], "{other_marker}", ["up", 0]),
        "cap": _primitive_multiline("caption text"),
        "tpl": _primitive_multiline("template text"),
        "up": _primitive_multiline("user prompt original"),
    }

    with pytest.raises(ValueError) as exc:
        _resolve_positive_prompt_target(workflow, workflow["pos"])

    message = str(exc.value)
    assert "pos" in message


# --------------------------------------------------------------------------- #
# 6. str 分支回归保护
# --------------------------------------------------------------------------- #
def test_resolve_positive_prompt_target_str_branch_returns_text_field():
    workflow: WorkflowDict = {
        "pos": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "plain positive string"},
        },
    }

    target_id, target_field = _resolve_positive_prompt_target(
        workflow, workflow["pos"]
    )

    assert target_id == "pos"
    assert target_field == "text"


# --------------------------------------------------------------------------- #
# 7. _LATENT_CLASS_TYPES 常量包含两个 latent 类型
# --------------------------------------------------------------------------- #
def test_latent_class_types_includes_both_empty_latent_classes():
    assert "EmptyLatentImage" in _LATENT_CLASS_TYPES
    assert "EmptySD3LatentImage" in _LATENT_CLASS_TYPES


# --------------------------------------------------------------------------- #
# 8. _load_workflow_context 不抛错 + _extract_workflow_defaults 默认值
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


# --------------------------------------------------------------------------- #
# 9. caption 注入：caption_prompt 覆盖节点 44，不影响节点 48
# --------------------------------------------------------------------------- #
def test_patch_workflow_newbie_caption_injects_on_node_44() -> None:
    workflow = load_workflow(NEWBIE_WORKFLOW)

    patched = patch_workflow(
        workflow,
        positive_prompt=XML_PROMPT,
        negative_prompt="neg",
        caption_prompt="A close-up portrait of Amiya from Arknights.",
    )

    # caption 写入节点 44 (PrimitiveStringMultiline "Caption")
    assert _inputs(patched["44"]).get("value") == (
        "A close-up portrait of Amiya from Arknights."
    )
    # 正向 XML 仍正常注入节点 48
    assert _inputs(patched["48"]).get("value") == XML_PROMPT
    # 引用链完整
    assert _inputs(patched["41:53"]).get("text") == ["46", 0]


def test_patch_workflow_newbie_caption_none_does_not_touch_node_44() -> None:
    workflow = load_workflow(NEWBIE_WORKFLOW)
    original_caption = _inputs(workflow["44"]).get("value")

    patched = patch_workflow(
        workflow,
        positive_prompt=XML_PROMPT,
        negative_prompt="neg",
    )

    assert _inputs(patched["44"]).get("value") == original_caption


def test_patch_workflow_newbie_caption_empty_string_skips_injection() -> None:
    workflow = load_workflow(NEWBIE_WORKFLOW)
    original_caption = _inputs(workflow["44"]).get("value")

    patched = patch_workflow(
        workflow,
        positive_prompt=XML_PROMPT,
        negative_prompt="neg",
        caption_prompt="",
    )

    assert _inputs(patched["44"]).get("value") == original_caption


def test_patch_workflow_newbie_caption_whitespace_only_skips_injection() -> None:
    workflow = load_workflow(NEWBIE_WORKFLOW)
    original_caption = _inputs(workflow["44"]).get("value")

    patched = patch_workflow(
        workflow,
        positive_prompt=XML_PROMPT,
        negative_prompt="neg",
        caption_prompt="   ",
    )

    assert _inputs(patched["44"]).get("value") == original_caption


# --------------------------------------------------------------------------- #
# 10. 两种 sentinel 互不干扰：caption 命中外层，user_prompt 命中内层
# --------------------------------------------------------------------------- #
def test_trace_sentinel_target_finds_caption_and_user_prompt_independently() -> None:
    workflow: WorkflowDict = {
        "pos": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": ["sr_outer", 0]},
        },
        "sr_outer": _string_replace_node(["sr_inner", 0], "{caption}", ["cap", 0]),
        "sr_inner": _string_replace_node(
            ["tpl", 0], "{user_prompt}", ["up", 0]
        ),
        "cap": _primitive_multiline("caption text"),
        "tpl": _primitive_multiline("template text"),
        "up": _primitive_multiline("user prompt original"),
    }

    # caption sentinel 命中外层（sr_outer, find={caption}）
    caption_target = _resolve_optional_sentinel_target(
        workflow, workflow["pos"], _CAPTION_SENTINEL
    )
    assert caption_target == ("cap", "value")

    # user_prompt sentinel 命中内层（sr_inner, find={user_prompt}）
    user_target = _resolve_positive_prompt_target(workflow, workflow["pos"])
    assert user_target == ("up", "value")


def test_resolve_optional_sentinel_target_returns_none_for_str_text() -> None:
    """common family 正向 text 为字符串时，宽松入口返回 None。"""
    workflow: WorkflowDict = {
        "pos": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "plain positive string"},
        },
    }

    result = _resolve_optional_sentinel_target(
        workflow, workflow["pos"], _CAPTION_SENTINEL
    )

    assert result is None