# pyright: basic, reportMissingImports=false, reportUnusedCallResult=false

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.prompt_grid import build_prompt_cell
from scripts.comfyui_part1_generate import build_parser, main


COMFY_ENV_KEYS = [
    "COMFYUI_X_CSV",
    "COMFYUI_Y_CSV",
    "COMFYUI_BASE_URL",
    "COMFYUI_WORKFLOW_JSON",
    "COMFYUI_OUT_DIR",
    "COMFYUI_CLIENT_ID",
    "COMFYUI_REQUEST_TIMEOUT_S",
    "COMFYUI_JOB_TIMEOUT_S",
    "COMFYUI_NEGATIVE_PROMPT",
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


def _write_csv_inputs(tmp_path: Path) -> tuple[Path, Path]:
    x_csv = tmp_path / "x.csv"
    y_csv = tmp_path / "y.csv"

    with x_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "Gender tags",
                "Character(s) tags",
                "Series tags",
                "Rating tags",
                "General tags",
                "Qulity tags",
            ]
        )
        writer.writerow(
            ["1girl,", "amiya,", "arknights,", "safe,", "solo,", "masterpiece,"]
        )

    with y_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Artists"])
        writer.writerow(["artist-a,"])
        writer.writerow(["artist-b,"])

    return x_csv, y_csv


def _read_valid_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def test_cli_help_contains_required_flags() -> None:
    help_text = build_parser().format_help()

    for flag in [
        "--x-csv",
        "--y-csv",
        "--template",
        "--base-seed",
        "--workflow-json",
        "--ksampler-node-id",
        "--x-limit",
        "--y-limit",
        "--x-indexes",
        "--y-indexes",
        "--run-dir",
        "--dry-run",
        "--base-url",
        "--request-timeout-s",
        "--job-timeout-s",
        "--client-id",
        "--negative-prompt",
        "--width",
        "--height",
        "--batch-size",
        "--steps",
        "--cfg",
        "--denoise",
        "--sampler-name",
        "--scheduler",
    ]:
        assert flag in help_text


def test_dry_run_loads_utf8_env_writes_run_json_and_prints_example(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_comfy_env(monkeypatch)
    x_csv, y_csv = _write_csv_inputs(tmp_path)
    run_dir = tmp_path / "run-dry"

    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "COMFYUI_BASE_URL=http://example.local:8188",
                "COMFYUI_WORKFLOW_JSON=missing-workflow.json",
                "COMFYUI_NEGATIVE_PROMPT=低质量,bad anatomy,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "--dry-run",
            "--x-csv",
            str(x_csv),
            "--y-csv",
            str(y_csv),
            "--run-dir",
            str(run_dir),
            "--base-seed",
            "123",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "组合总数: 2" in output
    assert "示例正向提示词:" in output

    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["dry_run"] is True
    assert run_payload["workflow_status"] == "not_loaded"
    assert run_payload["workflow_json_sha256"] == "not_loaded"
    assert run_payload["workflow_json_path"] == "missing-workflow.json"
    assert run_payload["comfyui_base_url"] == "http://example.local:8188"
    assert (
        run_payload["generation_overrides"]["negative_prompt"] == "低质量,bad anatomy,"
    )

    metadata_records = _read_valid_jsonl(run_dir / "metadata.jsonl")
    assert len(metadata_records) == 2
    assert all(record["status"] == "skipped" for record in metadata_records)
    assert all(record["workflow_hash"] == "not_loaded" for record in metadata_records)


def test_dry_run_does_not_call_comfyui_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_comfy_env(monkeypatch)
    x_csv, y_csv = _write_csv_inputs(tmp_path)
    run_dir = tmp_path / "run-no-comfy"

    def should_not_be_called(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        raise AssertionError("dry-run 不应调用 ComfyUI 客户端")

    monkeypatch.setattr(
        "scripts.comfyui_part1_generate.comfy_ws_connect", should_not_be_called
    )
    monkeypatch.setattr(
        "scripts.comfyui_part1_generate.comfy_submit_prompt", should_not_be_called
    )
    monkeypatch.setattr(
        "scripts.comfyui_part1_generate.comfy_ws_wait_prompt_done", should_not_be_called
    )
    monkeypatch.setattr(
        "scripts.comfyui_part1_generate.comfy_get_history_item", should_not_be_called
    )
    monkeypatch.setattr(
        "scripts.comfyui_part1_generate.comfy_download_image_to_path",
        should_not_be_called,
    )

    exit_code = main(
        [
            "--dry-run",
            "--x-csv",
            str(x_csv),
            "--y-csv",
            str(y_csv),
            "--run-dir",
            str(run_dir),
            "--base-seed",
            "99",
        ]
    )

    assert exit_code == 0


def test_resume_skip_map_ignores_broken_last_line_and_requires_existing_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_comfy_env(monkeypatch)
    x_csv, y_csv = _write_csv_inputs(tmp_path)
    run_dir = tmp_path / "run-resume"
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
    y_row = {"y": "artist-a,"}
    cell = build_prompt_cell(x_row, y_row, base_seed=99, x_index=0, y_index=0)

    existing_image = images_dir / "x0-y0.png"
    existing_image.write_bytes(b"png")

    metadata_path = run_dir / "metadata.jsonl"
    metadata_path.write_text(
        json.dumps(
            {
                "status": "success",
                "x_index": 0,
                "y_index": 0,
                "prompt_hash": cell["prompt_hash"],
                "seed": cell["seed"],
                "workflow_hash": "not_loaded",
                "local_image_path": "images/x0-y0.png",
            },
            ensure_ascii=False,
        )
        + "\n"
        + '{"status": "broken"',
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--dry-run",
            "--x-csv",
            str(x_csv),
            "--y-csv",
            str(y_csv),
            "--run-dir",
            str(run_dir),
            "--base-seed",
            "99",
            "--x-limit",
            "1",
            "--y-limit",
            "1",
        ]
    )

    assert exit_code == 0

    metadata_records = _read_valid_jsonl(metadata_path)
    assert len(metadata_records) == 2
    assert metadata_records[-1]["status"] == "skipped"
    assert metadata_records[-1]["skip_reason"] == "resume_hit"


def test_env_csv_paths_used_when_cli_flags_not_provided(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_comfy_env(monkeypatch)
    x_csv = tmp_path / "x-env.csv"
    y_csv = tmp_path / "y-env.csv"

    with x_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "Gender tags",
                "Character(s) tags",
                "Series tags",
                "Rating tags",
                "General tags",
                "Qulity tags",
            ]
        )
        writer.writerow(
            ["1girl,", "character-a,", "series-a,", "safe,", "solo,", "best,"]
        )

    with y_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Artists"])
        writer.writerow(["artist-from-env,"])

    run_dir = tmp_path / "run-env-test"

    (tmp_path / ".env").write_text(
        "\n".join(
            [
                f"COMFYUI_X_CSV={x_csv}",
                f"COMFYUI_Y_CSV={y_csv}",
                "COMFYUI_BASE_URL=http://example.local:8188",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "--dry-run",
            "--run-dir",
            str(run_dir),
            "--base-seed",
            "42",
        ]
    )

    assert exit_code == 0

    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["x_csv_path"] == str(x_csv)
    assert run_payload["y_csv_path"] == str(y_csv)
