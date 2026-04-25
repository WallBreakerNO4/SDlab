# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportPrivateUsage=false, reportAttributeAccessIssue=false, reportUnusedCallResult=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownLambdaType=false

import argparse
import importlib
import sys
import types
from pathlib import Path
from typing import Protocol, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generation.runner_env import _resolve_append_negative_prompt
from scripts.generation.prompt_grid import X_INFO_TYPE_KEY

DEFAULT_APPEND = "nsfw, nipples, pussy, nude,"


def _install_runner_config_stub() -> None:
    module = types.ModuleType("scripts.generation.runner_config")

    def load_runner_config(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        raise AssertionError("测试需显式 monkeypatch load_runner_config")

    setattr(module, "load_runner_config", load_runner_config)
    sys.modules["scripts.generation.runner_config"] = module


class _Outcome(Protocol):
    record: object | None
    download: object | None


class _WorkflowContextFactory(Protocol):
    def __call__(
        self,
        *,
        workflow: dict[str, object],
        workflow_json_path: str,
        workflow_hash: str,
        selected_ksampler_id: str,
        default_negative_prompt: str | None,
        default_params: dict[str, object],
    ) -> object: ...


class _CellPlanFactory(Protocol):
    def __call__(
        self,
        *,
        x_index: int,
        y_index: int,
        x_row: dict[str, str],
        y_value: str,
        positive_prompt: str,
        prompt_hash: str,
        seed: int,
        generation_params: dict[str, object],
        workflow_hash: str,
        save_image_prefix: str,
        x_description: dict[str, str],
    ) -> object: ...


class _RunnerModule(Protocol):
    WorkflowContext: _WorkflowContextFactory
    _CellPlan: _CellPlanFactory

    def _append_negative_prompt(self, base: str | None, append: str | None) -> str: ...
    def _worker_submit_and_wait(
        self,
        args: argparse.Namespace,
        run_dir: object,
        workflow_context: object,
        plan: object,
    ) -> _Outcome: ...


def _import_runner_module() -> _RunnerModule:
    _install_runner_config_stub()
    _ = sys.modules.pop("scripts.generation.comfyui_part1_generate", None)
    return cast(
        _RunnerModule,
        cast(
            object, importlib.import_module("scripts.generation.comfyui_part1_generate")
        ),
    )


def test_append_negative_prompt_with_both_base_and_append_provided() -> None:
    runner = _import_runner_module()
    assert (
        runner._append_negative_prompt("lowres, bad anatomy,", "nsfw, nipples,")
        == "lowres, bad anatomy, nsfw, nipples,"
    )


def test_append_negative_prompt_base_without_comma_uses_comma_space() -> None:
    runner = _import_runner_module()
    assert (
        runner._append_negative_prompt("lowres, bad anatomy", "nsfw, nipples,")
        == "lowres, bad anatomy, nsfw, nipples,"
    )


def test_append_negative_prompt_with_append_having_leading_commas_and_spaces() -> None:
    runner = _import_runner_module()
    assert (
        runner._append_negative_prompt("lowres,", ", , nsfw, nipples,")
        == "lowres, nsfw, nipples,"
    )


def test_append_negative_prompt_base_empty_returns_cleaned_append() -> None:
    runner = _import_runner_module()
    assert runner._append_negative_prompt("", "  nsfw, nipples,  ") == "nsfw, nipples,"


def test_append_negative_prompt_base_is_none_treats_as_empty() -> None:
    runner = _import_runner_module()
    assert runner._append_negative_prompt(None, "nsfw, nipples,") == "nsfw, nipples,"


def test_append_negative_prompt_append_is_empty_returns_base() -> None:
    runner = _import_runner_module()
    assert (
        runner._append_negative_prompt("lowres, bad anatomy,", "")
        == "lowres, bad anatomy,"
    )


def test_append_negative_prompt_both_empty_returns_empty() -> None:
    runner = _import_runner_module()
    assert runner._append_negative_prompt("", "") == ""


def test_resolve_append_negative_prompt_missing_env_returns_default() -> None:
    assert _resolve_append_negative_prompt(None) == DEFAULT_APPEND


def test_resolve_append_negative_prompt_empty_string_returns_none() -> None:
    assert _resolve_append_negative_prompt("") is None


def test_resolve_append_negative_prompt_custom_value_returns_stripped() -> None:
    assert _resolve_append_negative_prompt("  nsfw, nude,  ") == "nsfw, nude,"


def _build_worker_args(
    *,
    negative_prompt: str | None = None,
    append_negative_prompt: str | None = None,
) -> argparse.Namespace:
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
        negative_prompt=negative_prompt,
        append_negative_prompt=append_negative_prompt,
    )


def _build_worker_context(
    runner: _RunnerModule, default_negative_prompt: str | None
) -> object:
    return runner.WorkflowContext(
        workflow={},
        workflow_json_path="workflow.json",
        workflow_hash="wf-hash",
        selected_ksampler_id="3",
        default_negative_prompt=default_negative_prompt,
        default_params={},
    )


def _build_worker_plan(runner: _RunnerModule, x_info_type: str) -> object:
    x_row = {
        "gender": "1girl,",
        "characters": "amiya,",
        "series": "arknights,",
        "rating": "safe,",
        "general": "solo,",
        X_INFO_TYPE_KEY: x_info_type,
    }
    return runner._CellPlan(
        x_index=0,
        y_index=1,
        x_row=x_row,
        y_value="artist-a,",
        positive_prompt="1girl,amiya,",
        prompt_hash="hash1234",
        seed=42,
        generation_params={"seed": 42},
        workflow_hash="wf-hash",
        save_image_prefix="run/x0-y1",
        x_description={"zh": "", "en": ""},
    )


def test_negative_prompt_append_uses_config_value_and_ignores_env_for_normal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _import_runner_module()
    args = _build_worker_args(
        negative_prompt=None,
        append_negative_prompt="nsfw, nipples,",
    )
    workflow_context = _build_worker_context(runner, default_negative_prompt="lowres,")
    captured_negative_prompts: list[str] = []

    def fake_patch_workflow(
        *args: object, **kwargs: object
    ) -> dict[str, dict[str, str]]:
        _ = args
        negative_prompt = kwargs.get("negative_prompt")
        assert isinstance(negative_prompt, str)
        captured_negative_prompts.append(negative_prompt)
        return {"3": {}}

    monkeypatch.setenv("COMFYUI_APPEND_NEGATIVE_PROMPT", "from-env,")
    monkeypatch.setattr(runner, "patch_workflow", fake_patch_workflow)
    monkeypatch.setattr(
        runner, "comfy_submit_prompt", lambda *args, **kwargs: "pid-123"
    )
    monkeypatch.setattr(
        runner,
        "comfy_wait_prompt_done_with_fallback",
        lambda *args, **kwargs: None,
        raising=False,
    )

    normal_outcome = runner._worker_submit_and_wait(
        args,
        None,
        workflow_context,
        _build_worker_plan(runner, "normal"),
    )
    non_normal_outcome = runner._worker_submit_and_wait(
        args,
        None,
        workflow_context,
        _build_worker_plan(runner, "lora"),
    )

    assert normal_outcome.record is None
    assert normal_outcome.download is not None
    assert non_normal_outcome.record is None
    assert non_normal_outcome.download is not None
    assert captured_negative_prompts == ["lowres, nsfw, nipples,", "lowres,"]


def test_negative_prompt_append_uses_config_value_with_override_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _import_runner_module()
    args = _build_worker_args(
        negative_prompt="manual override",
        append_negative_prompt=", custom append,",
    )
    workflow_context = _build_worker_context(
        runner, default_negative_prompt="workflow default,"
    )
    captured_negative_prompts: list[str] = []

    def fake_patch_workflow(
        *args: object, **kwargs: object
    ) -> dict[str, dict[str, str]]:
        _ = args
        negative_prompt = kwargs.get("negative_prompt")
        assert isinstance(negative_prompt, str)
        captured_negative_prompts.append(negative_prompt)
        return {"3": {}}

    monkeypatch.setenv("COMFYUI_APPEND_NEGATIVE_PROMPT", "from-env-should-be-ignored,")
    monkeypatch.setattr(runner, "patch_workflow", fake_patch_workflow)
    monkeypatch.setattr(
        runner, "comfy_submit_prompt", lambda *args, **kwargs: "pid-456"
    )
    monkeypatch.setattr(
        runner,
        "comfy_wait_prompt_done_with_fallback",
        lambda *args, **kwargs: None,
        raising=False,
    )

    outcome = runner._worker_submit_and_wait(
        args,
        None,
        workflow_context,
        _build_worker_plan(runner, "normal"),
    )

    assert outcome.record is None
    assert outcome.download is not None
    assert captured_negative_prompts == ["manual override, custom append,"]


def test_final_negative_prompt_for_x_row_uses_args_append_and_ignores_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _import_runner_module()
    args = _build_worker_args(
        negative_prompt=None,
        append_negative_prompt="config-append,",
    )
    workflow_context = _build_worker_context(runner, default_negative_prompt="lowres,")
    monkeypatch.setenv("COMFYUI_APPEND_NEGATIVE_PROMPT", "from-env,")

    normal_prompt = runner._final_negative_prompt_for_x_row(
        args,
        workflow_context,
        {X_INFO_TYPE_KEY: "normal"},
    )
    lora_prompt = runner._final_negative_prompt_for_x_row(
        args,
        workflow_context,
        {X_INFO_TYPE_KEY: "lora"},
    )

    assert normal_prompt == "lowres, config-append,"
    assert lora_prompt == "lowres,"


def test_final_negative_prompt_for_x_row_append_only_normal() -> None:
    runner = _import_runner_module()
    args = _build_worker_args(
        negative_prompt=None,
        append_negative_prompt="only-append,",
    )
    # 即使 workflow_context 缺失或默认值为 None
    workflow_context = _build_worker_context(runner, default_negative_prompt=None)

    normal_prompt = runner._final_negative_prompt_for_x_row(
        args,
        workflow_context,
        {X_INFO_TYPE_KEY: "normal"},
    )
    assert normal_prompt == "only-append,"


def test_final_negative_prompt_for_x_row_append_only_non_normal_returns_none() -> None:
    runner = _import_runner_module()
    args = _build_worker_args(
        negative_prompt=None,
        append_negative_prompt="only-append,",
    )
    workflow_context = _build_worker_context(runner, default_negative_prompt=None)

    lora_prompt = runner._final_negative_prompt_for_x_row(
        args,
        workflow_context,
        {X_INFO_TYPE_KEY: "lora"},
    )
    assert lora_prompt is None
