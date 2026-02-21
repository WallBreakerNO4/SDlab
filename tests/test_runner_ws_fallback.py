# pyright: basic, reportMissingImports=false, reportUnusedCallResult=false

import argparse
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generation.comfyui_client import ComfyUIClientError
from scripts.generation import comfyui_part1_generate as runner


def _build_args() -> argparse.Namespace:
    return argparse.Namespace(
        client_id="test-client",
        base_url="http://127.0.0.1:8188",
        request_timeout_s=1.0,
        job_timeout_s=2.0,
        steps=None,
        cfg=None,
        denoise=None,
        sampler_name=None,
        scheduler=None,
        width=None,
        height=None,
        batch_size=None,
        negative_prompt=None,
    )


def _build_workflow_context() -> runner.WorkflowContext:
    return runner.WorkflowContext(
        workflow={},
        workflow_json_path="workflow.json",
        workflow_hash="wf-hash",
        selected_ksampler_id="3",
        default_negative_prompt="neg,",
        default_params={},
    )


def _build_plan() -> runner._CellPlan:
    return runner._CellPlan(
        x_index=0,
        y_index=1,
        x_row={
            "gender": "1girl,",
            "characters": "amiya,",
            "series": "arknights,",
            "rating": "safe,",
            "general": "solo,",
            "quality": "masterpiece,",
        },
        y_value="artist-a,",
        positive_prompt="1girl,amiya,",
        prompt_hash="hash1234",
        seed=42,
        generation_params={"seed": 42},
        workflow_hash="wf-hash",
        save_image_prefix="run/x0-y1",
        x_description={"zh": "", "en": ""},
    )


def test_worker_submit_and_wait_uses_fallback_wait_and_returns_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _build_args()
    workflow_context = _build_workflow_context()
    plan = _build_plan()

    called: dict[str, object] = {}

    monkeypatch.setattr(runner, "patch_workflow", lambda *args, **kwargs: {"3": {}})
    monkeypatch.setattr(
        runner, "comfy_submit_prompt", lambda *args, **kwargs: "pid-123"
    )

    def fake_wait_with_fallback(*args: object, **kwargs: object) -> None:
        _ = args
        called["kwargs"] = kwargs

    monkeypatch.setattr(
        runner,
        "comfy_wait_prompt_done_with_fallback",
        fake_wait_with_fallback,
        raising=False,
    )

    def fail_if_ws_called(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        raise AssertionError("runner 不应直接调用 comfy_ws_connect")

    monkeypatch.setattr(
        "scripts.generation.comfyui_client.comfy_ws_connect",
        fail_if_ws_called,
    )

    outcome = runner._worker_submit_and_wait(args, workflow_context, plan)

    assert outcome.record is None
    assert outcome.download is not None
    assert outcome.download.prompt_id == "pid-123"
    kwargs = called["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["base_url"] == "http://127.0.0.1:8188"
    assert kwargs["prompt_id"] == "pid-123"
    assert kwargs["request_timeout_s"] == 1.0
    assert kwargs["job_timeout_s"] == 2.0
    client_id = kwargs["client_id"]
    assert isinstance(client_id, str)
    assert client_id.startswith("test-client-")


def test_worker_submit_and_wait_serializes_execution_error_as_failed_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _build_args()
    workflow_context = _build_workflow_context()
    plan = _build_plan()

    monkeypatch.setattr(runner, "patch_workflow", lambda *args, **kwargs: {"3": {}})
    monkeypatch.setattr(
        runner, "comfy_submit_prompt", lambda *args, **kwargs: "pid-err"
    )

    def fake_wait_with_fallback(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        raise ComfyUIClientError(
            "execution failed",
            code="execution_error",
            context={"prompt_id": "pid-err", "node_id": "12"},
        )

    monkeypatch.setattr(
        runner,
        "comfy_wait_prompt_done_with_fallback",
        fake_wait_with_fallback,
        raising=False,
    )

    def fail_if_ws_called(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        raise AssertionError("runner 不应直接调用 comfy_ws_connect")

    monkeypatch.setattr(
        "scripts.generation.comfyui_client.comfy_ws_connect",
        fail_if_ws_called,
    )

    outcome = runner._worker_submit_and_wait(args, workflow_context, plan)

    assert outcome.download is None
    assert outcome.record is not None
    assert outcome.record["status"] == "failed"
    assert outcome.record["comfyui_prompt_id"] == "pid-err"
    assert outcome.record["error"] == {
        "code": "execution_error",
        "message": "execution failed",
        "context": {"prompt_id": "pid-err", "node_id": "12"},
    }
