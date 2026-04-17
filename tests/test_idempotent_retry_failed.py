# pyright: basic, reportMissingImports=false, reportUnusedCallResult=false

import hashlib
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_minimal_run_json(
    run_dir: Path,
    x_json: Path,
    y_json: Path,
) -> None:
    run_payload = {
        "x_json_path": str(x_json),
        "y_json_path": str(y_json),
        "template": runner.DEFAULT_TEMPLATE,
        "quality_prompt": "masterpiece, best quality,",
        "base_seed": 100,
        "workflow_api_path": "workflow.json",
        "workflow_api_sha256": "wf-hash",
        "x_json_sha256": _sha256_file(x_json),
        "y_json_sha256": _sha256_file(y_json),
        "config_snapshot": {
            "workflow": {
                "api_path": "data/models/example/api.json",
                "api_sha256": "wf-hash",
                "download_path": "data/models/example/workflow.json",
                "download_sha256": "download-sha",
                "ksampler_node_id": None,
            }
        },
        "generation_overrides": {
            "negative_prompt": None,
            "width": None,
            "height": None,
            "batch_size": None,
            "steps": None,
            "cfg": None,
            "denoise": None,
            "sampler_name": None,
            "scheduler": None,
        },
        "selection": {"x_indexes": [0], "y_indexes": [0]},
    }
    (run_dir / "run.json").write_text(
        json.dumps(run_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _stub_generation(
    monkeypatch: pytest.MonkeyPatch,
    submit_counter: dict[str, int],
    workflow_hash: str,
    seen_args: dict[str, object],
) -> None:
    monkeypatch.setattr(
        runner,
        "_load_workflow_context",
        lambda args: (
            seen_args.update(
                {
                    "append_negative_prompt": getattr(
                        args, "append_negative_prompt", None
                    ),
                    "ksampler_node_id": getattr(args, "ksampler_node_id", None),
                }
            )
            or runner.WorkflowContext(
                workflow={},
                workflow_json_path=str(args.workflow_json),
                workflow_hash=workflow_hash,
                selected_ksampler_id="3",
                default_negative_prompt="neg,",
                default_params={},
            )
        ),
    )
    monkeypatch.setattr(runner, "patch_workflow", lambda *args, **kwargs: {"3": {}})

    def fake_submit_prompt(*args: object, **kwargs: object) -> str:
        _ = (args, kwargs)
        submit_counter["count"] += 1
        return "pid-1"

    monkeypatch.setattr(runner, "comfy_submit_prompt", fake_submit_prompt)
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


def test_retry_failed_is_idempotent_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_comfy_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    x_json, y_json = _write_single_cell_inputs(tmp_path)
    run_dir = tmp_path / "run-retry-idempotent"
    (run_dir / "images").mkdir(parents=True, exist_ok=True)
    _write_minimal_run_json(run_dir, x_json, y_json)

    workflow_hash = "wf-hash"
    x_row = {
        "gender": "1girl,",
        "characters": "amiya,",
        "series": "arknights,",
        "rating": "safe,",
        "general": "solo,",
    }
    y_value = "artist-a,"
    prompt_hash = runner.compute_prompt_hash(
        render_positive_prompt(x_row, y_value, "masterpiece, best quality,")
    )
    seed = derive_seed(100, 0, 0)

    initial_failed = {
        "status": "failed",
        "x_index": 0,
        "y_index": 0,
        "prompt_hash": prompt_hash,
        "seed": seed,
        "workflow_api_sha256": workflow_hash,
        "attempt": 1,
        "error": {"code": "network_timeout"},
    }
    (run_dir / "metadata.jsonl").write_text(
        json.dumps(initial_failed, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    submit_counter = {"count": 0}
    seen_args: dict[str, object] = {}
    _stub_generation(monkeypatch, submit_counter, workflow_hash, seen_args)

    first_exit = runner.main(["--retry-failed", "--run-dir", str(run_dir)])
    first_output = capsys.readouterr()

    assert first_exit == 0
    assert "参数错误" not in first_output.err
    assert "运行失败" not in first_output.err
    assert submit_counter["count"] == 1
    assert seen_args["append_negative_prompt"] is None
    assert seen_args["ksampler_node_id"] is None

    records_after_first = _read_jsonl(run_dir / "metadata.jsonl")
    assert len(records_after_first) == 2
    assert records_after_first[-1]["status"] == "success"
    assert records_after_first[-1]["attempt"] == 2
    assert records_after_first[-1]["local_image_path"] == "images/x0-y0.png"
    assert (run_dir / "images" / "x0-y0.png").exists()

    second_exit = runner.main(["--retry-failed", "--run-dir", str(run_dir)])
    second_output = capsys.readouterr()

    assert second_exit == 0
    assert "参数错误" not in second_output.err
    assert "运行失败" not in second_output.err
    assert submit_counter["count"] == 1

    records_after_second = _read_jsonl(run_dir / "metadata.jsonl")
    assert len(records_after_second) == 2
