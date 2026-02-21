# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportPrivateUsage=false

import argparse
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generation.comfyui_part1_generate import (
    _append_negative_prompt,
    _resolve_append_negative_prompt,
)
from scripts.generation import comfyui_part1_generate as runner
from scripts.generation.prompt_grid import X_INFO_TYPE_KEY

DEFAULT_APPEND = "nsfw, nipples, pussy, nude,"


def test_append_negative_prompt_with_both_base_and_append_provided():
    """base 和 append 都提供，base 以逗号结尾 -> 用单个空格连接"""
    base = "lowres, bad anatomy,"
    append = "nsfw, nipples,"
    result = _append_negative_prompt(base, append)
    assert result == "lowres, bad anatomy, nsfw, nipples,"


def test_append_negative_prompt_base_without_comma_uses_comma_space():
    """base 没有以逗号结尾 -> 用 ', ' 连接"""
    base = "lowres, bad anatomy"
    append = "nsfw, nipples,"
    result = _append_negative_prompt(base, append)
    assert result == "lowres, bad anatomy, nsfw, nipples,"


def test_append_negative_prompt_with_append_having_leading_commas_and_spaces():
    """append 有前导逗号和空格 -> 应该被清理"""
    base = "lowres,"
    append = ", , nsfw, nipples,"
    result = _append_negative_prompt(base, append)
    assert result == "lowres, nsfw, nipples,"


def test_append_negative_prompt_base_empty_returns_cleaned_append():
    """base 为空 -> 返回清理后的 append"""
    base = ""
    append = "  nsfw, nipples,  "
    result = _append_negative_prompt(base, append)
    assert result == "nsfw, nipples,"


def test_append_negative_prompt_base_is_none_treats_as_empty():
    """base 为 None -> 视为空字符串"""
    base = None
    append = "nsfw, nipples,"
    result = _append_negative_prompt(base, append)
    assert result == "nsfw, nipples,"


def test_append_negative_prompt_append_is_empty_returns_base():
    """append 为空字符串 -> 返回 base"""
    base = "lowres, bad anatomy,"
    append = ""
    result = _append_negative_prompt(base, append)
    assert result == "lowres, bad anatomy,"


def test_append_negative_prompt_both_empty_returns_empty():
    """base 和 append 都为空 -> 返回空字符串"""
    base = ""
    append = ""
    result = _append_negative_prompt(base, append)
    assert result == ""


def test_append_negative_prompt_base_whitespace_only_treated_as_empty():
    """base 只有空白字符 -> 视为空"""
    base = "   \t\n  "
    append = "nsfw, nipples,"
    result = _append_negative_prompt(base, append)
    assert result == "nsfw, nipples,"


def test_append_negative_prompt_append_with_only_spaces():
    """append 只有空格 -> strip 后为空，返回 base"""
    base = "lowres,"
    append = "   "
    result = _append_negative_prompt(base, append)
    assert result == "lowres,"


def test_append_negative_prompt_base_ends_with_comma_space():
    """base 以 ', ' 结尾（多个空格）-> strip 后去尾空格，用单空格连接"""
    base = "lowres, bad anatomy,   "
    append = "nsfw, nipples,"
    result = _append_negative_prompt(base, append)
    assert result == "lowres, bad anatomy, nsfw, nipples,"


def test_append_negative_prompt_append_is_none():
    """append 为 None -> 视为空字符串，返回 base"""
    base = "lowres,"
    append = None
    result = _append_negative_prompt(base, append)
    assert result == "lowres,"


def test_append_negative_prompt_default_append_used():
    """append 是默认字符串 -> 正确拼接"""
    base = "lowres,"
    append = DEFAULT_APPEND
    result = _append_negative_prompt(base, append)
    assert result == "lowres, nsfw, nipples, pussy, nude,"


def test_append_negative_prompt_complex_leading_cleanup():
    """复杂的前导清理：多个逗号和空格"""
    base = "lowres,"
    append = ",,   ,  nsfw, nipples,"
    result = _append_negative_prompt(base, append)
    assert result == "lowres, nsfw, nipples,"


def test_append_negative_prompt_base_without_trailing_comma_comma_space_delimiter():
    """base 没有逗号结尾但非空 -> 使用 ', ' 作为分隔符"""
    base = "lowres bad anatomy"
    append = "nsfw, nipples,"
    result = _append_negative_prompt(base, append)
    assert result == "lowres bad anatomy, nsfw, nipples,"


def test_append_negative_prompt_append_only_commas_returns_base():
    """append 只有逗号和空格，清理后为空 -> 返回 base，不加分隔符"""
    base = "lowres,"
    append = ",,,   ,,,"
    result = _append_negative_prompt(base, append)
    assert result == "lowres,"


def test_append_negative_prompt_append_only_spaces_returns_base():
    """append 只有空格，清理后为空 -> 返回 base，不加分隔符"""
    base = "lowres, bad anatomy,"
    append = "   "
    result = _append_negative_prompt(base, append)
    assert result == "lowres, bad anatomy,"


def test_resolve_append_negative_prompt_missing_env_returns_default():
    """raw 为 None（环境变量缺失） -> 返回默认字符串"""
    result = _resolve_append_negative_prompt(None)
    assert result == DEFAULT_APPEND


def test_resolve_append_negative_prompt_empty_string_returns_none():
    """raw 为空字符串（显式禁用） -> 返回 None"""
    result = _resolve_append_negative_prompt("")
    assert result is None


def test_resolve_append_negative_prompt_whitespace_only_returns_none():
    """raw 只有空格 -> 视为空字符串，返回 None"""
    result = _resolve_append_negative_prompt("   \t\n  ")
    assert result is None


def test_resolve_append_negative_prompt_custom_value_returns_stripped():
    """raw 有自定义值 -> 返回 stripped 后的值"""
    result = _resolve_append_negative_prompt("  nsfw, nude,  ")
    assert result == "nsfw, nude,"


def test_resolve_append_negative_prompt_comma_terminated_value_preserved():
    """raw 以逗号结尾 -> strip 后保持逗号结尾"""
    result = _resolve_append_negative_prompt("  nsfw, nipples,  ")
    assert result == "nsfw, nipples,"


def _build_worker_args(negative_prompt: str | None = None) -> argparse.Namespace:
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
    )


def _build_worker_context(default_negative_prompt: str) -> runner.WorkflowContext:
    return runner.WorkflowContext(
        workflow={},
        workflow_json_path="workflow.json",
        workflow_hash="wf-hash",
        selected_ksampler_id="3",
        default_negative_prompt=default_negative_prompt,
        default_params={},
    )


def _build_worker_plan(x_info_type: str) -> runner._CellPlan:
    x_row = {
        "gender": "1girl,",
        "characters": "amiya,",
        "series": "arknights,",
        "rating": "safe,",
        "general": "solo,",
        "quality": "masterpiece,",
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


def test_negative_prompt_append_applies_only_to_normal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _build_worker_args()
    workflow_context = _build_worker_context(default_negative_prompt="lowres,")
    captured_negative_prompts: list[str] = []

    def fake_patch_workflow(
        *args: object, **kwargs: object
    ) -> dict[str, dict[str, str]]:
        _ = args
        negative_prompt = kwargs.get("negative_prompt")
        assert isinstance(negative_prompt, str)
        captured_negative_prompts.append(negative_prompt)
        return {"3": {}}

    monkeypatch.setenv("COMFYUI_APPEND_NEGATIVE_PROMPT", "nsfw, nipples,")
    monkeypatch.setattr(runner, "patch_workflow", fake_patch_workflow)

    def fake_submit_prompt(*args: object, **kwargs: object) -> str:
        _ = (args, kwargs)
        return "pid-123"

    def fake_wait_prompt_done_with_fallback(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(runner, "comfy_submit_prompt", fake_submit_prompt)
    monkeypatch.setattr(
        runner,
        "comfy_wait_prompt_done_with_fallback",
        fake_wait_prompt_done_with_fallback,
        raising=False,
    )

    normal_outcome = runner._worker_submit_and_wait(
        args,
        workflow_context,
        _build_worker_plan("normal"),
    )
    non_normal_outcome = runner._worker_submit_and_wait(
        args,
        workflow_context,
        _build_worker_plan("lora"),
    )

    assert normal_outcome.record is None
    assert normal_outcome.download is not None
    assert non_normal_outcome.record is None
    assert non_normal_outcome.download is not None
    assert captured_negative_prompts == ["lowres, nsfw, nipples,", "lowres,"]


def test_negative_prompt_append_uses_override_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _build_worker_args(negative_prompt="manual override")
    workflow_context = _build_worker_context(
        default_negative_prompt="workflow default,"
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

    monkeypatch.setenv("COMFYUI_APPEND_NEGATIVE_PROMPT", ", custom append,")
    monkeypatch.setattr(runner, "patch_workflow", fake_patch_workflow)

    def fake_submit_prompt(*args: object, **kwargs: object) -> str:
        _ = (args, kwargs)
        return "pid-456"

    def fake_wait_prompt_done_with_fallback(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(runner, "comfy_submit_prompt", fake_submit_prompt)
    monkeypatch.setattr(
        runner,
        "comfy_wait_prompt_done_with_fallback",
        fake_wait_prompt_done_with_fallback,
        raising=False,
    )

    outcome = runner._worker_submit_and_wait(
        args,
        workflow_context,
        _build_worker_plan("normal"),
    )

    assert outcome.record is None
    assert outcome.download is not None
    assert captured_negative_prompts == ["manual override, custom append,"]
