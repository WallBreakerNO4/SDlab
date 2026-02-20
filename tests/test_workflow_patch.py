# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import copy
import sys
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generation.workflow_patch import (
    WorkflowDict,
    WorkflowOverrides,
    load_workflow,
    patch_workflow,
)


RF_WORKFLOW = ROOT / "data" / "comfyui-flow" / "CKNOOBRF.json"
MAIN_WORKFLOW = ROOT / "data" / "comfyui-flow" / "CKNOOBmain.json"


def _inputs(node: dict[str, object]) -> dict[str, object]:
    inputs_obj = node.get("inputs")
    assert isinstance(inputs_obj, dict)
    return cast(dict[str, object], inputs_obj)


def test_load_workflow_reads_json_dict_from_file_path():
    workflow = load_workflow(RF_WORKFLOW)

    assert isinstance(workflow, dict)
    assert workflow["6"]["class_type"] == "KSampler"


def test_patch_workflow_reference_chasing_injects_rf_and_applies_overrides():
    workflow = load_workflow(RF_WORKFLOW)

    patched = patch_workflow(
        workflow,
        positive_prompt="pos prompt",
        negative_prompt="neg prompt",
        overrides=WorkflowOverrides(
            seed=123,
            steps=44,
            cfg=7.5,
            denoise=0.62,
            sampler_name="heun",
            scheduler="karras",
            width=896,
            height=1152,
            batch_size=3,
        ),
    )

    assert _inputs(patched["12"]).get("text") == "pos prompt"
    assert _inputs(patched["4"]).get("text") == "neg prompt"
    assert _inputs(patched["6"]).get("seed") == 123
    assert _inputs(patched["6"]).get("steps") == 44
    assert _inputs(patched["6"]).get("cfg") == 7.5
    assert _inputs(patched["6"]).get("denoise") == 0.62
    assert _inputs(patched["6"]).get("sampler_name") == "heun"
    assert _inputs(patched["6"]).get("scheduler") == "karras"
    assert _inputs(patched["5"]).get("width") == 896
    assert _inputs(patched["5"]).get("height") == 1152
    assert _inputs(patched["5"]).get("batch_size") == 3


def test_patch_workflow_reference_chasing_injects_main_with_tristate_none_unchanged():
    workflow = load_workflow(MAIN_WORKFLOW)
    original = copy.deepcopy(workflow)

    patched = patch_workflow(
        workflow,
        positive_prompt="main pos",
        negative_prompt="main neg",
        overrides=WorkflowOverrides(steps=31),
    )

    assert _inputs(patched["3"]).get("text") == "main pos"
    assert _inputs(patched["4"]).get("text") == "main neg"
    assert _inputs(patched["5"]).get("steps") == 31
    assert _inputs(patched["5"]).get("seed") == _inputs(original["5"]).get("seed")
    assert _inputs(patched["5"]).get("cfg") == _inputs(original["5"]).get("cfg")
    assert _inputs(patched["6"]).get("width") == _inputs(original["6"]).get("width")
    assert _inputs(patched["6"]).get("height") == _inputs(original["6"]).get("height")
    assert _inputs(patched["6"]).get("batch_size") == _inputs(original["6"]).get(
        "batch_size"
    )


def test_patch_workflow_overrides_save_image_filename_prefix_when_requested():
    workflow = load_workflow(MAIN_WORKFLOW)

    patched = patch_workflow(
        workflow,
        positive_prompt="main pos",
        negative_prompt="main neg",
        overrides=WorkflowOverrides(steps=31),
        save_image_prefix="run-test/x0-y0-s1-deadbeef",
    )

    save_nodes = [
        node for node in patched.values() if node.get("class_type") == "SaveImage"
    ]
    assert save_nodes
    for node in save_nodes:
        assert _inputs(node).get("filename_prefix") == "run-test/x0-y0-s1-deadbeef"


def test_patch_workflow_raises_clear_error_when_multiple_ksampler_without_selection():
    workflow = {
        "1": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "old-pos"},
            "_meta": {"title": "正向"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "old-neg"},
            "_meta": {"title": "负向"},
        },
        "3": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 768, "batch_size": 1},
            "_meta": {"title": "latent"},
        },
        "10": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["1", 0],
                "negative": ["2", 0],
                "latent_image": ["3", 0],
            },
            "_meta": {"title": "采样器-A"},
        },
        "11": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["1", 0],
                "negative": ["2", 0],
                "latent_image": ["3", 0],
            },
            "_meta": {"title": "采样器-B"},
        },
    }

    with pytest.raises(ValueError) as exc:
        _ = patch_workflow(
            cast(WorkflowDict, workflow),
            positive_prompt="new-pos",
            negative_prompt="new-neg",
        )

    message = str(exc.value)
    assert "multiple KSampler" in message
    assert "10" in message and "采样器-A" in message
    assert "11" in message and "采样器-B" in message


def test_patch_workflow_can_select_specific_ksampler_when_multiple_exist():
    workflow = {
        "1": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "old-pos-a"},
            "_meta": {"title": "正向-A"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "old-neg-a"},
            "_meta": {"title": "负向-A"},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "old-pos-b"},
            "_meta": {"title": "正向-B"},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "old-neg-b"},
            "_meta": {"title": "负向-B"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 512, "batch_size": 1},
            "_meta": {"title": "latent-a"},
        },
        "6": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 640, "height": 640, "batch_size": 2},
            "_meta": {"title": "latent-b"},
        },
        "10": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["1", 0],
                "negative": ["2", 0],
                "latent_image": ["5", 0],
                "steps": 20,
            },
            "_meta": {"title": "采样器-A"},
        },
        "11": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["6", 0],
                "steps": 30,
            },
            "_meta": {"title": "采样器-B"},
        },
    }

    patched = patch_workflow(
        cast(WorkflowDict, workflow),
        positive_prompt="picked-pos",
        negative_prompt="picked-neg",
        ksampler_node_id="11",
        overrides=WorkflowOverrides(batch_size=4),
    )

    assert _inputs(patched["3"]).get("text") == "picked-pos"
    assert _inputs(patched["4"]).get("text") == "picked-neg"
    assert _inputs(patched["6"]).get("batch_size") == 4
    assert _inputs(patched["1"]).get("text") == "old-pos-a"
    assert _inputs(patched["2"]).get("text") == "old-neg-a"
    assert _inputs(patched["5"]).get("batch_size") == 1
