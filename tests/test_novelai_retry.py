# pyright: basic, reportMissingImports=false, reportUnusedCallResult=false, reportPrivateUsage=false

"""NovelAI retry 接线测试：守卫硬停后 --retry-failed/--retry-incomplete/--retry-error-code 的恢复路径。

照 test_retry_incomplete_integration.py 先例伪造 run 目录（run.json + metadata.jsonl），
钉外部可观察行为：目标 cell 选择、错误码过滤、strict 一致性校验拒绝。
"""

from __future__ import annotations

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

from scripts.generation import novelai_generate
from scripts.generation.novelai_client import NovelAIAnlasGuardError
from scripts.generation.prompt_grid import compute_prompt_hash, derive_seed, read_y_rows_for_novelai
from scripts.generation.runner_prompt_template import (
    _render_prompt_by_template as render_prompt,
)

MODEL_KEY = "nai-diffusion-5-full"
TEMPLATE = "{gender}{characters}{series}{y}{rating}{general}{quality}"
QUALITY_PROMPT = "year 2025, very aesthetic, masterpiece, no text,"
NEGATIVE_PROMPT = (
    "lowres, artistic error, scan artifacts, worst quality, bad quality,"
    " jpeg artifacts, multiple views,"
)
APPEND_NEGATIVE_PROMPT = "nsfw,nipples,pussy,nude,"
BASE_SEED = 123

GUARD_CODE_BATTERY_LOW = "anlas_battery_low"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_xy_inputs(tmp_path: Path) -> tuple[Path, Path]:
    x_json = tmp_path / "x.json"
    y_json = tmp_path / "y.json"
    if x_json.exists() and y_json.exists():
        return x_json, y_json

    x_payload: dict[str, object] = {
        "items": [
            {
                "tags": {
                    "gender": [{"text": "1girl", "weight": 1.0}],
                    "characters": [{"text": "amiya", "weight": 1.0}],
                    "series": [{"text": "arknights", "weight": 1.0}],
                    "rating": [{"text": "general", "weight": 1.0}],
                    "general": [{"text": "solo", "weight": 1.0}],
                },
                "info": {"index": 0, "type": "normal"},
            }
        ],
    }
    y_payload: dict[str, object] = {
        "schema": "prompt-y-table/v3",
        "collection_id": "retry-test",
        "items": [
            {
                "tags": [{"text": "artist-a", "weight": 1.0, "type": "artists"}],
                "info": {"index": 0},
            },
            {
                "tags": [{"text": "artist-b", "weight": 1.0, "type": "artists"}],
                "info": {"index": 1},
            },
            {
                "tags": [{"text": "artist-c", "weight": 1.0, "type": "artists"}],
                "info": {"index": 2},
            },
        ],
    }

    x_json.write_text(json.dumps(x_payload, ensure_ascii=False) + "\n", encoding="utf-8")
    y_json.write_text(json.dumps(y_payload, ensure_ascii=False) + "\n", encoding="utf-8")
    return x_json, y_json


def _fingerprint_args() -> argparse.Namespace:
    return argparse.Namespace(
        negative_prompt=NEGATIVE_PROMPT,
        append_negative_prompt=APPEND_NEGATIVE_PROMPT,
        width=832,
        height=1216,
        batch_size=1,
        steps=28,
        cfg=5.0,
        denoise=None,
        sampler_name="k_euler_ancestral",
        scheduler=None,
    )


def _expected_fingerprint(model_key: str = MODEL_KEY) -> str:
    return novelai_generate._novelai_generation_fingerprint(
        _fingerprint_args(), model=model_key
    )


NOVELAI_DEFAULT_TEMPLATE = "{quality}{rating}{y}{gender}{characters}{series}{general}"


def _expected_prompt_hash(y_value: str) -> str:
    prompt = render_prompt(
        TEMPLATE,
        _x_row(),
        y_value,
        default_template=NOVELAI_DEFAULT_TEMPLATE,
        quality_prompt=QUALITY_PROMPT,
    )
    return compute_prompt_hash(prompt, None)


def _x_row() -> dict[str, str]:
    return {
        "gender": "1girl,",
        "characters": "amiya,",
        "series": "arknights,",
        "rating": "general,",
        "general": "solo,",
        "info_type": "normal",
    }


def _write_run_json(
    run_dir: Path,
    x_json: Path,
    y_json: Path,
    *,
    model_key: str = MODEL_KEY,
    backend: str = "novelai",
    y_indexes: list[int] | None = None,
) -> None:
    payload = {
        "backend": backend,
        "model": {"key": model_key},
        "x_json_path": str(x_json),
        "y_json_path": str(y_json),
        "template": TEMPLATE,
        "quality_prompt": QUALITY_PROMPT,
        "base_seed": BASE_SEED,
        "workflow_api_path": "",
        "workflow_api_sha256": _expected_fingerprint(model_key),
        "x_json_sha256": _sha256_file(x_json),
        "y_json_sha256": _sha256_file(y_json),
        "config_snapshot": {
            "workflow": {
                "api_sha256": _expected_fingerprint(model_key),
            }
        },
        "generation_overrides": {
            "negative_prompt": NEGATIVE_PROMPT,
            "append_negative_prompt": APPEND_NEGATIVE_PROMPT,
            "width": 832,
            "height": 1216,
            "batch_size": 1,
            "steps": 28,
            "cfg": 5.0,
            "denoise": None,
            "sampler_name": "k_euler_ancestral",
            "scheduler": None,
        },
        "selection": {
            "x_indexes": [0],
            "y_indexes": y_indexes if y_indexes is not None else [0, 1],
        },
    }
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _metadata_record(
    tmp_path: Path,
    *,
    status: str,
    x_index: int,
    y_index: int,
    error_code: str | None = None,
    with_image: bool = False,
    fingerprint: str | None = None,
    prompt_hash: str | None = None,
    seed: int | None = None,
    attempt: int = 1,
) -> dict[str, object]:
    # 记录构造依赖 y.json 渲染结果；先幂等落盘 XY 输入再读取。
    _write_xy_inputs(tmp_path)
    y_rows = read_y_rows_for_novelai(str(tmp_path / "y.json"))
    y_value = y_rows[y_index]["y"]

    record: dict[str, object] = {
        "status": status,
        "x_index": x_index,
        "y_index": y_index,
        "prompt_hash": (
            prompt_hash if prompt_hash is not None else _expected_prompt_hash(y_value)
        ),
        "seed": seed if seed is not None else derive_seed(BASE_SEED, x_index, y_index),
        "workflow_api_sha256": (
            fingerprint if fingerprint is not None else _expected_fingerprint()
        ),
        "attempt": attempt,
    }
    if error_code is not None:
        record["error"] = {"type": "anlas_guard", "code": error_code}
    if with_image:
        record["local_image_paths"] = [f"images/x{x_index}-y{y_index}.png"]
    return record


def _prepare_run_dir(
    tmp_path: Path,
    records: list[dict[str, object]],
    *,
    model_key: str = MODEL_KEY,
    backend: str = "novelai",
    y_indexes: list[int] | None = None,
) -> Path:
    x_json, y_json = _write_xy_inputs(tmp_path)
    run_dir = tmp_path / "hard-stopped-run"
    (run_dir / "images").mkdir(parents=True, exist_ok=True)
    _write_run_json(
        run_dir,
        x_json,
        y_json,
        model_key=model_key,
        backend=backend,
        y_indexes=y_indexes,
    )

    for record in records:
        if record.get("status") == "success":
            paths = record.get("local_image_paths")
            if isinstance(paths, list):
                for rel in paths:
                    image_path = run_dir / str(rel)
                    image_path.parent.mkdir(parents=True, exist_ok=True)
                    image_path.write_bytes(b"png")

    with (run_dir / "metadata.jsonl").open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return run_dir


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


# --- 参数校验 ---


def test_cli_help_contains_retry_flags() -> None:
    help_text = novelai_generate.build_parser().format_help()

    for flag in ["--retry-failed", "--retry-incomplete", "--retry-error-code"]:
        assert flag in help_text


def test_retry_failed_requires_run_dir(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = novelai_generate.main(["--retry-failed"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "retry 模式必须提供 --run-dir" in captured.err


def test_retry_failed_requires_existing_run_dir(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    non_existent = tmp_path / "does-not-exist"

    exit_code = novelai_generate.main(["--retry-failed", "--run-dir", str(non_existent)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "不存在或不是目录" in captured.err


def test_retry_error_code_requires_retry_mode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = tmp_path / "mock-run"
    run_dir.mkdir()

    exit_code = novelai_generate.main(
        [
            "--run-dir",
            str(run_dir),
            "--retry-error-code",
            GUARD_CODE_BATTERY_LOW,
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "仅可与 --retry-failed/--retry-incomplete 一起使用" in captured.err


def test_retry_error_code_empty_string(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = tmp_path / "mock-run"
    run_dir.mkdir()

    exit_code = novelai_generate.main(
        [
            "--retry-failed",
            "--run-dir",
            str(run_dir),
            "--retry-error-code",
            "",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--retry-error-code 不能为空" in captured.err


def test_fresh_run_requires_config(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = novelai_generate.main([])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--config" in captured.err


def test_retry_failed_without_run_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = tmp_path / "mock-run"
    run_dir.mkdir()

    exit_code = novelai_generate.main(["--retry-failed", "--run-dir", str(run_dir)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "run.json 不存在" in captured.err


def test_retry_rejects_non_novelai_run_dir(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    success = _metadata_record(
        tmp_path,
        status="success",
        x_index=0,
        y_index=0,
        with_image=True,
    )
    failed = _metadata_record(
        tmp_path,
        status="failed",
        x_index=0,
        y_index=1,
        error_code=GUARD_CODE_BATTERY_LOW,
    )
    run_dir = _prepare_run_dir(tmp_path, [success, failed], backend="comfyui")

    exit_code = novelai_generate.main(["--retry-failed", "--run-dir", str(run_dir)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "backend" in captured.err


# --- retry 选择与恢复（dry-run 驱动，观察 metadata.jsonl 增量）---


def test_retry_failed_recovers_only_failed_cells(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    success = _metadata_record(
        tmp_path,
        status="success",
        x_index=0,
        y_index=0,
        with_image=True,
    )
    failed_battery = _metadata_record(
        tmp_path,
        status="failed",
        x_index=0,
        y_index=1,
        error_code=GUARD_CODE_BATTERY_LOW,
    )
    run_dir = _prepare_run_dir(tmp_path, [success, failed_battery])

    exit_code = novelai_generate.main(
        ["--retry-failed", "--dry-run", "--run-dir", str(run_dir)]
    )

    assert exit_code == 0
    rows = _read_jsonl(run_dir / "metadata.jsonl")
    # 原始 2 条 + 只为失败格补 1 条 dry-run 记录；成功格不得重跑。
    assert len(rows) == 3
    new_records = [row for row in rows if row.get("skip_reason") == "dry_run"]
    assert len(new_records) == 1
    assert new_records[0]["x_index"] == 0
    assert new_records[0]["y_index"] == 1
    # strict 一致性：新记录携带原 run 的指纹与派生 seed。
    assert new_records[0]["workflow_api_sha256"] == _expected_fingerprint()
    assert new_records[0]["seed"] == derive_seed(BASE_SEED, 0, 1)


def test_retry_error_code_filters_guard_hard_stop_cells(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failed_network = _metadata_record(
        tmp_path,
        status="failed",
        x_index=0,
        y_index=0,
        error_code="network_error",
    )
    failed_battery = _metadata_record(
        tmp_path,
        status="failed",
        x_index=0,
        y_index=1,
        error_code=GUARD_CODE_BATTERY_LOW,
    )
    failed_billing = _metadata_record(
        tmp_path,
        status="failed",
        x_index=0,
        y_index=2,
        error_code="anlas_billing_detected",
    )
    run_dir = _prepare_run_dir(
        tmp_path, [failed_network, failed_battery, failed_billing], y_indexes=[0, 1, 2]
    )

    exit_code = novelai_generate.main(
        [
            "--retry-failed",
            "--retry-error-code",
            GUARD_CODE_BATTERY_LOW,
            "--dry-run",
            "--run-dir",
            str(run_dir),
        ]
    )

    assert exit_code == 0
    rows = _read_jsonl(run_dir / "metadata.jsonl")
    new_records = [row for row in rows if row.get("skip_reason") == "dry_run"]
    assert len(new_records) == 1
    assert new_records[0]["y_index"] == 1


def test_retry_failed_without_error_code_targets_all_failed_cells(
    tmp_path: Path,
) -> None:
    failed_network = _metadata_record(
        tmp_path,
        status="failed",
        x_index=0,
        y_index=0,
        error_code="network_error",
    )
    failed_battery = _metadata_record(
        tmp_path,
        status="failed",
        x_index=0,
        y_index=1,
        error_code=GUARD_CODE_BATTERY_LOW,
    )
    run_dir = _prepare_run_dir(tmp_path, [failed_network, failed_battery])

    exit_code = novelai_generate.main(
        ["--retry-failed", "--dry-run", "--run-dir", str(run_dir)]
    )

    assert exit_code == 0
    rows = _read_jsonl(run_dir / "metadata.jsonl")
    new_records = [row for row in rows if row.get("skip_reason") == "dry_run"]
    assert {row["y_index"] for row in new_records} == {0, 1}


def test_retry_incomplete_recovers_missing_cells(
    tmp_path: Path,
) -> None:
    success_with_image = _metadata_record(
        tmp_path,
        status="success",
        x_index=0,
        y_index=0,
        with_image=True,
    )
    success_missing_image = _metadata_record(
        tmp_path,
        status="success",
        x_index=0,
        y_index=1,
        with_image=False,
    )
    run_dir = _prepare_run_dir(tmp_path, [success_with_image, success_missing_image])

    exit_code = novelai_generate.main(
        ["--retry-incomplete", "--dry-run", "--run-dir", str(run_dir)]
    )

    assert exit_code == 0
    rows = _read_jsonl(run_dir / "metadata.jsonl")
    new_records = [row for row in rows if row.get("skip_reason") == "dry_run"]
    assert len(new_records) == 1
    assert new_records[0]["y_index"] == 1


# --- strict 一致性校验拒绝 ---


def test_retry_rejects_prompt_hash_change(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failed = _metadata_record(
        tmp_path,
        status="failed",
        x_index=0,
        y_index=1,
        error_code=GUARD_CODE_BATTERY_LOW,
        prompt_hash="0" * 64,
    )
    run_dir = _prepare_run_dir(tmp_path, [failed])

    exit_code = novelai_generate.main(
        ["--retry-failed", "--dry-run", "--run-dir", str(run_dir)]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "retry strict 校验失败(prompt_hash)" in captured.err


def test_retry_rejects_seed_change(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failed = _metadata_record(
        tmp_path,
        status="failed",
        x_index=0,
        y_index=1,
        error_code=GUARD_CODE_BATTERY_LOW,
        seed=999,
    )
    run_dir = _prepare_run_dir(tmp_path, [failed])

    exit_code = novelai_generate.main(
        ["--retry-failed", "--dry-run", "--run-dir", str(run_dir)]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "retry strict 校验失败(seed)" in captured.err


def test_retry_rejects_fingerprint_change(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failed = _metadata_record(
        tmp_path,
        status="failed",
        x_index=0,
        y_index=1,
        error_code=GUARD_CODE_BATTERY_LOW,
        fingerprint="f" * 64,
    )
    run_dir = _prepare_run_dir(tmp_path, [failed])

    exit_code = novelai_generate.main(
        ["--retry-failed", "--dry-run", "--run-dir", str(run_dir)]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "retry strict 校验失败(workflow_api_sha256)" in captured.err


# --- 非 dry-run 真实恢复路径（Fake client 驱动 worker 全链路）---


class _FakeImage:
    def save(self, path: str, format: str) -> None:  # noqa: A002
        _ = format
        Path(path).write_bytes(b"rgba-png")


class _FakeGuardClient:
    def __init__(self, *, api_key: str | None = None, **kwargs: Any) -> None:
        # 模拟环境变量已提供 key 的场景，让入口通过 key 存在性检查。
        self._api_key = api_key or "fake-key"
        self.calls: list[dict[str, object]] = []

    def preflight(self, *, model: str | None = None) -> None:
        _ = model
        return None

    def generate(self, **kwargs: Any) -> list[_FakeImage]:
        self.calls.append(kwargs)
        return [_FakeImage()]


def test_retry_failed_runs_worker_and_writes_rgba_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed = _metadata_record(
        tmp_path,
        status="failed",
        x_index=0,
        y_index=1,
        error_code=GUARD_CODE_BATTERY_LOW,
    )
    run_dir = _prepare_run_dir(tmp_path, [failed])

    created_clients: list[_FakeGuardClient] = []

    def fake_client_factory(*args: Any, **kwargs: Any) -> _FakeGuardClient:
        client = _FakeGuardClient(*args, **kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(novelai_generate, "NovelAIAPIClient", fake_client_factory)

    exit_code = novelai_generate.main(["--retry-failed", "--run-dir", str(run_dir)])

    assert exit_code == 0
    assert len(created_clients) == 1

    image_path = run_dir / "images" / "x0-y1.png"
    assert image_path.exists()
    assert image_path.read_bytes() == b"rgba-png"

    rows = _read_jsonl(run_dir / "metadata.jsonl")
    latest: dict[tuple[int, int], dict[str, object]] = {}
    for row in rows:
        key = (int(row["x_index"]), int(row["y_index"]))  # type: ignore[arg-type]
        latest[key] = row
    recovered = latest[(0, 1)]
    assert recovered["status"] == "success"
    assert recovered["attempt"] == 2
    assert recovered["workflow_api_sha256"] == _expected_fingerprint()


def test_retry_battery_low_hard_stop_leaves_remaining_cells_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """电量耗尽触发真中止：停止提交剩余格子，未提交格子保持 incomplete。"""
    failed_first = _metadata_record(
        tmp_path,
        status="failed",
        x_index=0,
        y_index=1,
        error_code=GUARD_CODE_BATTERY_LOW,
    )
    failed_second = _metadata_record(
        tmp_path,
        status="failed",
        x_index=0,
        y_index=2,
        error_code=GUARD_CODE_BATTERY_LOW,
    )
    run_dir = _prepare_run_dir(
        tmp_path,
        [failed_first, failed_second],
        y_indexes=[0, 1, 2],
    )

    class _BatteryDrainedClient:
        def __init__(self, *, api_key: str | None = None, **kwargs: Any) -> None:
            self._api_key = api_key or "fake-key"
            self.calls: list[dict[str, object]] = []

        def preflight(self, *, model: str | None = None) -> None:
            _ = model
            return None

        def generate(self, **kwargs: Any) -> list[_FakeImage]:
            self.calls.append(kwargs)
            raise NovelAIAnlasGuardError(
                "V5 电量耗尽：usage.isNegative=true",
                code=GUARD_CODE_BATTERY_LOW,
            )

    created: list[_BatteryDrainedClient] = []

    def fake_client_factory(*args: Any, **kwargs: Any) -> _BatteryDrainedClient:
        client = _BatteryDrainedClient(*args, **kwargs)
        created.append(client)
        return client

    monkeypatch.setattr(novelai_generate, "NovelAIAPIClient", fake_client_factory)

    # 并发固定为 1，保证第二格在首格中止后才被调度（可确定性断言未提交）。
    exit_code = novelai_generate.main(
        ["--retry-failed", "--concurrency", "1", "--run-dir", str(run_dir)]
    )

    assert exit_code == 1
    # 首格电量检查即失败并触发中止：第二格从未提交。
    assert len(created) == 1
    assert len(created[0].calls) == 1

    rows = _read_jsonl(run_dir / "metadata.jsonl")
    counts: dict[tuple[int, int], list[dict[str, object]]] = {}
    for row in rows:
        key = (int(row["x_index"]), int(row["y_index"]))  # type: ignore[arg-type]
        counts.setdefault(key, []).append(row)

    # 首格：新增一条 battery_low 失败记录（attempt 2）。
    assert len(counts[(0, 1)]) == 2
    new_record = counts[(0, 1)][-1]
    assert new_record["status"] == "failed"
    error = new_record["error"]
    assert isinstance(error, dict)
    assert error["code"] == GUARD_CODE_BATTERY_LOW
    assert new_record["attempt"] == 2

    # 第二格：中止后未提交，没有新记录，保持 incomplete（仅剩 fixture 原记录）。
    assert len(counts[(0, 2)]) == 1
    assert counts[(0, 2)][0]["attempt"] == 1
