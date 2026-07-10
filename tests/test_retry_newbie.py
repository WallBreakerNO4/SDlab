# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportPrivateUsage=false

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generation import comfyui_part1_generate as runner
from scripts.generation.prompt_grid import (
    _NEWBIE_SYSTEM_PROMPT,
    assemble_newbie_prompt,
    compute_prompt_hash,
    derive_seed,
    read_x_rows_newbie,
    read_y_rows,
)


QUALITY_PROMPT = "masterpiece, best quality"
WORKFLOW_HASH = "workflow-hash"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_newbie_inputs(tmp_path: Path) -> tuple[Path, Path]:
    x_path = tmp_path / "newbie-x.yaml"
    y_path = tmp_path / "newbie-y.yaml"
    x_path.write_text(
        """schema: newbie-x-table/v1
items:
  - characters:
      - n: amiya (arknights)
        gender: 1girl
        appearance: brown hair, blue eyes
    general:
      count: 1girl, solo
      style: anime
    info:
      type: normal
    caption:
      en: A close-up portrait of Amiya from Arknights.
""",
        encoding="utf-8",
    )
    y_path.write_text(
        """schema: prompt-y-table/v3
items:
  - tags:
      - text: artist-a
        weight: 1.0
        type: artists
    info:
      index: 0
""",
        encoding="utf-8",
    )
    return x_path, y_path


def _write_retry_fixture(
    tmp_path: Path,
    *,
    prompt_hash_override: str | None = None,
) -> tuple[Path, str]:
    x_path, y_path = _write_newbie_inputs(tmp_path)
    x_row = read_x_rows_newbie(x_path)[0]
    y_value = read_y_rows(y_path)[0]["y"]
    rendered_prompt = assemble_newbie_prompt(
        x_row,
        y_value,
        quality_prompt=QUALITY_PROMPT,
    )
    prompt_hash = prompt_hash_override or compute_prompt_hash(rendered_prompt)

    run_dir = tmp_path / "run-newbie-retry"
    run_dir.mkdir()
    run_payload: dict[str, object] = {
        "x_json_path": str(x_path),
        "y_json_path": str(y_path),
        "template": "{quality}{y}{general}",
        "quality_prompt": QUALITY_PROMPT,
        "base_seed": 123,
        "workflow_api_path": None,
        "x_json_sha256": _sha256_file(x_path),
        "y_json_sha256": _sha256_file(y_path),
        "generation_overrides": {
            "negative_prompt": (
                "<e621_tags>furry</e621_tags>\n"
                "<danbooru_tags>lowres</danbooru_tags>\n"
                "<resolution>low_resolution</resolution>"
            ),
            "append_negative_prompt": "nsfw",
            "width": 832,
            "height": 1216,
            "batch_size": 1,
            "steps": 28,
            "cfg": 5.0,
            "denoise": 1.0,
            "sampler_name": "res_multistep",
            "scheduler": "linear_quadratic",
        },
        "selection": {"x_indexes": [0], "y_indexes": [0]},
        "model": {
            "key": "newbie-image-exp01",
            "name": "NewBie-image Exp0.1",
            "family": "newbie",
            "artist_weight_profile": "identity",
        },
        "config_snapshot": {
            "workflow": {"ksampler_node_id": None},
        },
    }
    (run_dir / "run.json").write_text(
        json.dumps(run_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    metadata_record = {
        "status": "failed",
        "x_index": 0,
        "y_index": 0,
        "prompt_hash": prompt_hash,
        "seed": derive_seed(123, 0, 0),
        "workflow_api_sha256": WORKFLOW_HASH,
        "attempt": 1,
        "error": {"code": "network_timeout"},
    }
    (run_dir / "metadata.jsonl").write_text(
        json.dumps(metadata_record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return run_dir, rendered_prompt


def _build_retry_args(run_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        config=None,
        dry_run=False,
        retry_failed=True,
        retry_incomplete=False,
        retry_error_code=None,
        run_dir=str(run_dir),
        client_id="test-client",
        base_url="http://127.0.0.1:8188",
        request_timeout_s=1.0,
        job_timeout_s=2.0,
        concurrency=1,
    )


def _patch_generation_collaborators(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runner,
        "_load_workflow_context",
        lambda args: runner.WorkflowContext(
            workflow={},
            workflow_json_path=str(args.workflow_json),
            workflow_hash=WORKFLOW_HASH,
            selected_ksampler_id="41:3",
            default_negative_prompt="",
            default_params={},
        ),
    )

    def unexpected_call(*args: object, **kwargs: object) -> Any:
        _ = (args, kwargs)
        raise AssertionError("纯本地 retry 测试不应调用 ComfyUI 或网络协作者")

    for attribute in (
        "patch_workflow",
        "comfy_submit_prompt",
        "comfy_wait_prompt_done_with_fallback",
        "comfy_get_history_item",
        "comfy_download_image_to_path",
    ):
        monkeypatch.setattr(runner, attribute, unexpected_call)


def test_run_retry_newbie_uses_family_reader_and_xml_renderer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, expected_prompt = _write_retry_fixture(tmp_path)
    _patch_generation_collaborators(monkeypatch)
    actual_newbie_reader = runner.read_x_rows_newbie
    reader_calls = {"newbie": 0, "common": 0}
    captured: dict[str, object] = {}

    def tracked_newbie_reader(path: str | Path) -> list[dict[str, object]]:
        reader_calls["newbie"] += 1
        return actual_newbie_reader(path)

    def forbidden_common_reader(path: str | Path) -> list[dict[str, str]]:
        _ = path
        reader_calls["common"] += 1
        raise AssertionError("newbie retry 不应调用 common X reader")

    def fake_run_generation(**kwargs: object) -> bool:
        captured["scheduled"] = True
        args = kwargs["args"]
        x_selected = kwargs["x_selected"]
        y_selected = kwargs["y_selected"]
        render_prompt = kwargs["render_prompt"]
        assert isinstance(args, argparse.Namespace)
        rendered = render_prompt(
            args.template,
            x_selected[0].value,
            y_selected[0].value["y"],
        )
        captured["rendered"] = rendered
        captured["model_family"] = args.model_family
        return False

    monkeypatch.setattr(runner, "read_x_rows_newbie", tracked_newbie_reader)
    monkeypatch.setattr(runner, "read_x_rows", forbidden_common_reader)
    monkeypatch.setattr(runner, "run_generation", fake_run_generation)

    exit_code = runner.run_retry(_build_retry_args(run_dir))

    assert exit_code == 0
    assert reader_calls == {"newbie": 1, "common": 0}
    assert captured["scheduled"] is True
    assert captured["model_family"] == "newbie"
    assert captured["rendered"] == expected_prompt
    assert expected_prompt.startswith(f"{_NEWBIE_SYSTEM_PROMPT}\n<image>\n")
    assert (
        "<caption>A close-up portrait of Amiya from Arknights.</caption>"
        in expected_prompt
    )
    assert "<character_1>" in expected_prompt
    assert "<n>amiya (arknights)</n>" in expected_prompt
    assert "<general_tags>" in expected_prompt
    assert "<artists>artist-a</artists>" in expected_prompt
    assert expected_prompt.endswith("</image>")


def test_run_retry_newbie_rejects_wrong_prompt_hash_before_scheduling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, _ = _write_retry_fixture(
        tmp_path,
        prompt_hash_override="wrong-prompt-hash",
    )
    _patch_generation_collaborators(monkeypatch)
    scheduled = {"value": False}

    def fake_run_generation(**kwargs: object) -> bool:
        _ = kwargs
        scheduled["value"] = True
        return False

    monkeypatch.setattr(runner, "run_generation", fake_run_generation)

    with pytest.raises(ValueError, match=r"retry strict 校验失败\(prompt_hash\)"):
        runner.run_retry(_build_retry_args(run_dir))

    assert scheduled["value"] is False
