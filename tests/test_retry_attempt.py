# pyright: basic, reportMissingImports=false, reportUnusedCallResult=false

import argparse
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generation import comfyui_part1_generate as runner
from scripts.generation.prompt_grid import derive_seed, render_positive_prompt


COMFY_ENV_KEYS = [
    "COMFYUI_X_JSON",
    "COMFYUI_Y_JSON",
    "COMFYUI_TEMPLATE",
    "COMFYUI_BASE_URL",
    "COMFYUI_WORKFLOW_JSON",
    "COMFYUI_OUT_DIR",
    "COMFYUI_CLIENT_ID",
    "COMFYUI_REQUEST_TIMEOUT_S",
    "COMFYUI_JOB_TIMEOUT_S",
    "COMFYUI_CONCURRENCY",
    "COMFYUI_NEGATIVE_PROMPT",
    "COMFYUI_APPEND_NEGATIVE_PROMPT",
    "COMFYUI_WIDTH",
    "COMFYUI_HEIGHT",
    "COMFYUI_BATCH_SIZE",
    "COMFYUI_STEPS",
    "COMFYUI_CFG",
    "COMFYUI_DENOISE",
    "COMFYUI_SAMPLER_NAME",
    "COMFYUI_SCHEDULER",
]


def _clear_comfy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in COMFY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _write_single_cell_inputs(tmp_path: Path) -> tuple[Path, Path]:
    x_json = tmp_path / "x.json"
    y_json = tmp_path / "y.json"

    x_payload: dict[str, object] = {
        "schema": "",
        "items": [
            {
                "tags": {
                    "gender": [{"text": "1girl", "weight": 1.0}],
                    "characters": [{"text": "amiya", "weight": 1.0}],
                    "series": [{"text": "arknights", "weight": 1.0}],
                    "rating": [{"text": "safe", "weight": 1.0}],
                    "general": [{"text": "solo", "weight": 1.0}],
                    "quality": [{"text": "masterpiece", "weight": 1.0}],
                },
                "info": {"index": 0, "type": "sfw"},
            }
        ],
    }
    y_payload: dict[str, object] = {
        "schema": "prompt-y-table/v2",
        "items": [
            {
                "tags": [{"text": "artist-a", "weight": 1.0}],
                "info": {"index": 0, "type": "artists"},
            }
        ],
    }

    x_json.write_text(
        json.dumps(x_payload, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    y_json.write_text(
        json.dumps(y_payload, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return x_json, y_json


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _stub_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runner,
        "_load_workflow_context",
        lambda args: runner.WorkflowContext(
            workflow={},
            workflow_json_path=str(args.workflow_json),
            workflow_hash="wf-hash",
            selected_ksampler_id="3",
            default_negative_prompt="neg,",
            default_params={},
        ),
    )
    monkeypatch.setattr(runner, "patch_workflow", lambda *args, **kwargs: {"3": {}})
    monkeypatch.setattr(runner, "comfy_submit_prompt", lambda *args, **kwargs: "pid-1")
    monkeypatch.setattr(
        runner,
        "comfy_wait_prompt_done_with_fallback",
        lambda *args, **kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        runner,
        "comfy_get_history_item",
        lambda *args, **kwargs: {
            "outputs": {
                "9": {
                    "images": [
                        {
                            "filename": "mock.png",
                            "subfolder": "",
                            "type": "output",
                        }
                    ]
                }
            }
        },
    )

    def fake_download(*args: object, **kwargs: object) -> Path:
        _ = args
        output_path = kwargs.get("output_path")
        assert isinstance(output_path, Path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"png")
        return output_path

    monkeypatch.setattr(runner, "comfy_download_image_to_path", fake_download)


def _build_runner_args(
    *,
    x_json: Path,
    y_json: Path,
    run_dir: Path,
    base_seed: int,
    dry_run: bool,
    workflow_json: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        config=None,
        dry_run=dry_run,
        retry_failed=False,
        retry_incomplete=False,
        retry_error_code=None,
        run_dir=str(run_dir),
        client_id="test-client",
        base_url="http://127.0.0.1:8188",
        request_timeout_s=1.0,
        job_timeout_s=2.0,
        concurrency=1,
        x_json=str(x_json),
        y_json=str(y_json),
        template="{gender}{characters}{series}{rating}{y}{general}{quality}",
        base_seed=base_seed,
        workflow_json=workflow_json,
        ksampler_node_id="3",
        negative_prompt="neg,",
        append_negative_prompt=None,
        width=None,
        height=None,
        batch_size=1,
        steps=28,
        cfg=5.5,
        denoise=1.0,
        sampler_name="euler",
        scheduler="normal",
        x_limit=1,
        y_limit=1,
        x_indexes="0",
        y_indexes="0",
    )


def test_next_attempt_pure_function_handles_increment_and_legacy() -> None:
    assert runner._next_attempt(None, increment=False) == 1
    assert runner._next_attempt(None, increment=True) == 1

    assert runner._next_attempt({"attempt": 3}, increment=False) == 3
    assert runner._next_attempt({"attempt": 3}, increment=True) == 4

    assert runner._next_attempt({"status": "success"}, increment=False) == 1
    assert runner._next_attempt({"status": "success"}, increment=True) == 2


def test_dry_run_writes_attempt_one_when_no_previous_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_comfy_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    x_json, y_json = _write_single_cell_inputs(tmp_path)
    run_dir = tmp_path / "run-dry-attempt"

    exit_code = runner.run(
        _build_runner_args(
            x_json=x_json,
            y_json=y_json,
            run_dir=run_dir,
            base_seed=100,
            dry_run=True,
        )
    )

    assert exit_code == 0
    records = _read_jsonl(run_dir / "metadata.jsonl")
    assert len(records) == 1
    assert records[0]["attempt"] == 1
    assert isinstance(records[0]["attempt"], int)


def test_resume_hit_keeps_previous_attempt_without_increment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_comfy_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    x_json, y_json = _write_single_cell_inputs(tmp_path)
    run_dir = tmp_path / "run-resume-attempt"
    images_dir = run_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    x_row = {
        "gender": "1girl,",
        "characters": "amiya,",
        "series": "arknights,",
        "rating": "safe,",
        "general": "solo,",
        "quality": "masterpiece,",
    }
    y_value = "artist-a,"
    prompt_hash = runner.compute_prompt_hash(render_positive_prompt(x_row, y_value))
    seed = derive_seed(100, 0, 0)
    (images_dir / "x0-y0.png").write_bytes(b"png")

    (run_dir / "metadata.jsonl").write_text(
        json.dumps(
            {
                "status": "success",
                "x_index": 0,
                "y_index": 0,
                "prompt_hash": prompt_hash,
                "seed": seed,
                "workflow_hash": "not_loaded",
                "local_image_path": "images/x0-y0.png",
                "attempt": 4,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = runner.run(
        _build_runner_args(
            x_json=x_json,
            y_json=y_json,
            run_dir=run_dir,
            base_seed=100,
            dry_run=True,
        )
    )

    assert exit_code == 0
    records = _read_jsonl(run_dir / "metadata.jsonl")
    assert len(records) == 2
    assert records[-1]["status"] == "skipped"
    assert records[-1]["skip_reason"] == "resume_hit"
    assert records[-1]["attempt"] == 4


def test_dry_run_non_resume_uses_previous_attempt_without_increment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_comfy_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    x_json, y_json = _write_single_cell_inputs(tmp_path)
    run_dir = tmp_path / "run-dry-prev-attempt"
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "metadata.jsonl").write_text(
        json.dumps(
            {
                "status": "failed",
                "x_index": 0,
                "y_index": 0,
                "prompt_hash": "mismatch",
                "seed": 1,
                "workflow_hash": "mismatch",
                "attempt": 5,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = runner.run(
        _build_runner_args(
            x_json=x_json,
            y_json=y_json,
            run_dir=run_dir,
            base_seed=100,
            dry_run=True,
        )
    )

    assert exit_code == 0
    records = _read_jsonl(run_dir / "metadata.jsonl")
    assert len(records) == 2
    assert records[-1]["skip_reason"] == "dry_run"
    assert records[-1]["attempt"] == 5


def test_generation_attempt_increments_on_actual_rerun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_comfy_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _stub_generation(monkeypatch)
    x_json, y_json = _write_single_cell_inputs(tmp_path)
    run_dir = tmp_path / "run-gen-attempt"

    first_exit = runner.run(
        _build_runner_args(
            x_json=x_json,
            y_json=y_json,
            run_dir=run_dir,
            base_seed=100,
            dry_run=False,
            workflow_json="workflow.json",
        )
    )
    second_exit = runner.run(
        _build_runner_args(
            x_json=x_json,
            y_json=y_json,
            run_dir=run_dir,
            base_seed=101,
            dry_run=False,
            workflow_json="workflow.json",
        )
    )

    assert first_exit == 0
    assert second_exit == 0

    records = _read_jsonl(run_dir / "metadata.jsonl")
    assert len(records) == 2
    assert records[0]["status"] == "success"
    assert records[1]["status"] == "success"
    assert records[0]["attempt"] == 1
    assert records[1]["attempt"] == 2


def test_generation_legacy_record_without_attempt_uses_previous_as_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_comfy_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _stub_generation(monkeypatch)
    x_json, y_json = _write_single_cell_inputs(tmp_path)
    run_dir = tmp_path / "run-gen-legacy-attempt"
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "metadata.jsonl").write_text(
        json.dumps(
            {
                "status": "failed",
                "x_index": 0,
                "y_index": 0,
                "prompt_hash": "legacy",
                "seed": 1,
                "workflow_hash": "legacy",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = runner.run(
        _build_runner_args(
            x_json=x_json,
            y_json=y_json,
            run_dir=run_dir,
            base_seed=100,
            dry_run=False,
            workflow_json="workflow.json",
        )
    )

    assert exit_code == 0
    records = _read_jsonl(run_dir / "metadata.jsonl")
    assert len(records) == 2
    assert records[-1]["status"] == "success"
    assert records[-1]["attempt"] == 2
