# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.workflow_patch import (
    WorkflowOverrides,
    load_workflow,
    patch_workflow,
)


RF_WORKFLOW = ROOT / "data" / "comfyui-flow" / "CKNOOBRF.json"
MAIN_WORKFLOW = ROOT / "data" / "comfyui-flow" / "CKNOOBmain.json"


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

    assert patched["12"]["inputs"]["text"] == "pos prompt"
    assert patched["4"]["inputs"]["text"] == "neg prompt"
    assert patched["6"]["inputs"]["seed"] == 123
    assert patched["6"]["inputs"]["steps"] == 44
    assert patched["6"]["inputs"]["cfg"] == 7.5
    assert patched["6"]["inputs"]["denoise"] == 0.62
    assert patched["6"]["inputs"]["sampler_name"] == "heun"
    assert patched["6"]["inputs"]["scheduler"] == "karras"
    assert patched["5"]["inputs"]["width"] == 896
    assert patched["5"]["inputs"]["height"] == 1152
    assert patched["5"]["inputs"]["batch_size"] == 3


def test_patch_workflow_reference_chasing_injects_main_with_tristate_none_unchanged():
    workflow = load_workflow(MAIN_WORKFLOW)
    original = copy.deepcopy(workflow)

    patched = patch_workflow(
        workflow,
        positive_prompt="main pos",
        negative_prompt="main neg",
        overrides=WorkflowOverrides(steps=31),
    )

    assert patched["3"]["inputs"]["text"] == "main pos"
    assert patched["4"]["inputs"]["text"] == "main neg"
    assert patched["5"]["inputs"]["steps"] == 31
    assert patched["5"]["inputs"]["seed"] == original["5"]["inputs"]["seed"]
    assert patched["5"]["inputs"]["cfg"] == original["5"]["inputs"]["cfg"]
    assert patched["6"]["inputs"]["width"] == original["6"]["inputs"]["width"]
    assert patched["6"]["inputs"]["height"] == original["6"]["inputs"]["height"]
    assert patched["6"]["inputs"]["batch_size"] == original["6"]["inputs"]["batch_size"]


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
        patch_workflow(
            workflow,
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
        workflow,
        positive_prompt="picked-pos",
        negative_prompt="picked-neg",
        ksampler_node_id="11",
        overrides=WorkflowOverrides(batch_size=4),
    )

    assert patched["3"]["inputs"]["text"] == "picked-pos"
    assert patched["4"]["inputs"]["text"] == "picked-neg"
    assert patched["6"]["inputs"]["batch_size"] == 4
    assert patched["1"]["inputs"]["text"] == "old-pos-a"
    assert patched["2"]["inputs"]["text"] == "old-neg-a"
    assert patched["5"]["inputs"]["batch_size"] == 1
