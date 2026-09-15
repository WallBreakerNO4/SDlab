# pyright: basic, reportMissingImports=false, reportUnknownVariableType=false

"""发布快照状态判定：dry-run 计划输出与执行结果报告。

覆盖 issue #11 的状态判定与可观测输出合约：
- 计划单元格全部有图 → 已完结；缺格 / 坏元数据 / 坏图 → 进行中。
- `--complete` 人工收口为已完结。
- 快照当前指针带 `status` 与 `generated_cells`。
- 状态单调：网站当前快照已完结后，后续快照不回退为进行中。
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload import upload_planner as upload_planner_module
from scripts.r2_upload.manifest import rewrite_current_manifest_status
from scripts.r2_upload.upload_images_to_r2 import main
from scripts.r2_upload.upload_planner import _build_run_plan


@pytest.fixture(autouse=True)
def _isolated_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """把上传端的仓库根锚定到当前测试的临时目录，避免扫描真实 data/models。"""
    monkeypatch.setattr(upload_planner_module, "_REPO_ROOT", tmp_path)


def _write_png(path: Path, *, size: tuple[int, int] = (8, 6)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (10, 20, 30)).save(path, format="PNG")


def _run_json_for_cells(
    *,
    run_dir_name: str,
    total_cells: int,
    created_at: str = "2026-04-20T00:00:00Z",
) -> dict[str, object]:
    """构造带 selection 的最小 run.json：2 列 × 1 行。"""
    return {
        "run_id": run_dir_name,
        "run_key": run_dir_name,
        "run_dir": run_dir_name,
        "created_at": created_at,
        "selection": {
            "x_columns": [
                {"type": "normal", "description": {"zh": "列 1"}},
                {"type": "normal", "description": {"zh": "列 2"}},
            ],
            "y_indexes": [0],
            "x_count": 2,
            "y_count": 1,
            "total_cells": total_cells,
        },
    }


def _write_run_fixture(
    root: Path,
    *,
    run_name: str,
    metadata_records: list[dict[str, object]],
    total_cells: int = 2,
) -> Path:
    run_dir = root / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            _run_json_for_cells(
                run_dir_name=run_name,
                total_cells=total_cells,
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "metadata.jsonl").write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False) for record in metadata_records
        )
        + "\n",
        encoding="utf-8",
    )
    return run_dir


def _success_record(
    *,
    x_index: int,
    y_index: int,
    image_path: str,
) -> dict[str, object]:
    return {
        "status": "success",
        "x_index": x_index,
        "y_index": y_index,
        "x_info_type": "normal",
        "local_image_path": image_path,
    }


def _read_stdout_json(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    output = capsys.readouterr().out.strip()
    assert output
    lines = [line for line in output.splitlines() if line.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def _snapshot_stats(payload: dict[str, object]) -> list[dict[str, object]]:
    stats = payload.get("snapshot_stats")
    assert isinstance(stats, list)
    return [cast(dict[str, object], item) for item in stats]


def _current_manifest_from_plan(plan: object) -> dict[str, object]:
    uploads = cast(list[object], getattr(plan, "manifest_uploads"))
    matches = [
        upload
        for upload in uploads
        if getattr(upload, "variant", None) == "view_current"
    ]
    assert len(matches) == 1
    body_bytes = getattr(matches[0], "body_bytes")
    assert isinstance(body_bytes, bytes)
    parsed = json.loads(body_bytes.decode("utf-8"))
    assert isinstance(parsed, dict)
    return cast(dict[str, object], parsed)


def test_dry_run_reports_in_progress_when_cells_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_png(tmp_path / "cells-run/images/x0-y0.png")
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="cells-run",
        metadata_records=[_success_record(x_index=0, y_index=0, image_path="images/x0-y0.png")],
    )

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert _snapshot_stats(payload) == [
        {
            "run_dir": "cells-run",
            "status": "in_progress",
            "generated_cells": 1,
            "planned_cells": 2,
        }
    ]


def test_dry_run_reports_complete_when_all_cells_have_images(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_png(tmp_path / "full-run/images/x0-y0-a.png")
    _write_png(tmp_path / "full-run/images/x0-y0-b.png")
    _write_png(tmp_path / "full-run/images/x1-y0.png")
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="full-run",
        metadata_records=[
            {
                "status": "success",
                "x_index": 0,
                "y_index": 0,
                "x_info_type": "normal",
                "local_image_paths": [
                    "images/x0-y0-a.png",
                    "images/x0-y0-b.png",
                ],
            },
            _success_record(x_index=1, y_index=0, image_path="images/x1-y0.png"),
        ],
    )

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    # 多图单元格只计一次
    assert _snapshot_stats(payload) == [
        {
            "run_dir": "full-run",
            "status": "complete",
            "generated_cells": 2,
            "planned_cells": 2,
        }
    ]


def test_current_manifest_carries_status_and_generated_cells(
    tmp_path: Path,
) -> None:
    _write_png(tmp_path / "pointer-run/images/x0-y0.png")
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="pointer-run",
        metadata_records=[
            _success_record(x_index=0, y_index=0, image_path="images/x0-y0.png")
        ],
    )

    plan = _build_run_plan(
        run_dir,
        intermediate_root=tmp_path / "_r2_upload_intermediate",
        category_override=None,
        remaining_limit=None,
        image_workers=1,
    )

    manifest = _current_manifest_from_plan(plan)
    assert manifest["status"] == "in_progress"
    assert manifest["generated_cells"] == 1
    assert plan.snapshot_status == "in_progress"
    assert plan.generated_cells == 1
    assert plan.planned_cells == 2


def test_complete_flag_forces_complete_status(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_png(tmp_path / "forced-run/images/x0-y0.png")
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="forced-run",
        metadata_records=[
            _success_record(x_index=0, y_index=0, image_path="images/x0-y0.png")
        ],
    )

    exit_code = main(["--dry-run", "--complete", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert _snapshot_stats(payload) == [
        {
            "run_dir": "forced-run",
            "status": "complete",
            "generated_cells": 1,
            "planned_cells": 2,
        }
    ]


def test_complete_flag_is_rejected_with_all_runs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_root = tmp_path / "outputs"
    _write_png(run_root / "all-runs-run/images/x0-y0.png")
    _ = _write_run_fixture(
        run_root,
        run_name="all-runs-run",
        metadata_records=[
            _success_record(x_index=0, y_index=0, image_path="images/x0-y0.png")
        ],
    )

    exit_code = main(["--dry-run", "--complete", "--all-runs", "--run-root", str(run_root)])

    assert exit_code == 2
    assert capsys.readouterr().out.strip() == ""


def test_bad_metadata_lines_are_skipped_with_warning(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="bad-lines-run",
        metadata_records=[],
    )
    _write_png(run_dir / "images/x0-y0.png")
    metadata_line = json.dumps(
        _success_record(x_index=0, y_index=0, image_path="images/x0-y0.png")
    )
    # 最后一行是写入中断留下的非 UTF-8 残行，同样按坏行处理。
    (run_dir / "metadata.jsonl").write_bytes(
        (
            "\n".join(
                [
                    metadata_line,
                    "{not valid json",
                    "[1, 2, 3]",
                ]
            )
            + "\n"
        ).encode("utf-8")
        + b'\xff\xfe{"x":1}\n'
    )

    with caplog.at_level(logging.WARNING):
        exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert _snapshot_stats(payload) == [
        {
            "run_dir": "bad-lines-run",
            "status": "in_progress",
            "generated_cells": 1,
            "planned_cells": 2,
        }
    ]
    warnings = [record.message for record in caplog.records]
    assert any("metadata.jsonl" in message for message in warnings)
    assert sum(1 for message in warnings if "metadata.jsonl" in message) == 3


def test_bad_image_files_are_skipped_with_warning(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="bad-images-run",
        metadata_records=[],
    )
    corrupt_path = run_dir / "images/x0-y0.png"
    corrupt_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_path.write_bytes(b"not an image")
    (run_dir / "metadata.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    _success_record(
                        x_index=0, y_index=0, image_path="images/x0-y0.png"
                    )
                ),
                json.dumps(
                    _success_record(
                        x_index=1, y_index=0, image_path="images/missing.png"
                    )
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    stats = _snapshot_stats(payload)
    assert stats[0]["status"] == "in_progress"
    assert stats[0]["generated_cells"] == 0
    assert stats[0]["planned_cells"] == 2
    warnings = [record.message for record in caplog.records]
    assert sum(1 for message in warnings if "跳过" in message) == 2


def test_rewrite_current_manifest_status_preserves_other_fields() -> None:
    payload = json.dumps(
        {
            "schema_version": 2,
            "run_dir": "rewrite-run",
            "release_id": "abcdef123456",
            "status": "in_progress",
            "generated_cells": 1,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    rewritten = rewrite_current_manifest_status(payload, status="complete")
    parsed = json.loads(rewritten.decode("utf-8"))

    assert parsed["status"] == "complete"
    assert parsed["generated_cells"] == 1
    assert parsed["release_id"] == "abcdef123456"

    with pytest.raises(ValueError):
        rewrite_current_manifest_status(payload, status="unknown")


class _FakeR2Client:
    def __init__(self) -> None:
        self._objects: set[tuple[str, str]] = set()
        self._object_bodies: dict[tuple[str, str], bytes] = {}
        self.upload_calls = 0
        self.uploaded_keys: list[tuple[str, str]] = []

    def head_exists(self, bucket_name: str, key: str, *, bucket_scope: str) -> bool:
        _ = bucket_scope
        return (bucket_name, key) in self._objects

    def read_bytes_if_exists(
        self, bucket_name: str, key: str, *, bucket_scope: str
    ) -> bytes | None:
        _ = bucket_scope
        return self._object_bodies.get((bucket_name, key))

    def upload(self, plan: object) -> None:
        bucket_name = str(getattr(plan, "bucket_name"))
        key = str(getattr(plan, "key"))
        body_bytes = getattr(plan, "body_bytes", None)
        self._objects.add((bucket_name, key))
        self._object_bodies[(bucket_name, key)] = (
            body_bytes if isinstance(body_bytes, bytes) else b""
        )
        self.upload_calls += 1
        self.uploaded_keys.append((bucket_name, key))

    def body_for(self, key: str) -> bytes | None:
        return self._object_bodies.get(("dummy-public", key))

    def seed_object(self, bucket_name: str, key: str, body: bytes) -> None:
        self._objects.add((bucket_name, key))
        self._object_bodies[(bucket_name, key)] = body


class _CapturingSupabaseWriter:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def upsert_upload_index(
        self,
        payload: dict[str, object],
        *,
        progress_callback: Callable[[], None] | None = None,
    ) -> None:
        self.payloads.append(payload)
        if progress_callback is not None:
            images = payload.get("images")
            images_list = images if isinstance(images, list) else []
            for _ in range(1 + len(images_list)):
                progress_callback()


def _install_fake_backends(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fake_r2: _FakeR2Client,
    writer: _CapturingSupabaseWriter,
) -> None:
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "dummy-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "dummy-private")
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.SupabaseWriter.from_env",
        classmethod(lambda cls, dry_run, **kwargs: writer),
    )


def test_execute_reports_status_and_writes_it_through(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_png(tmp_path / "execute-status-run/images/x0-y0.png")
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="execute-status-run",
        metadata_records=[
            _success_record(x_index=0, y_index=0, image_path="images/x0-y0.png")
        ],
    )
    fake_r2 = _FakeR2Client()
    writer = _CapturingSupabaseWriter()
    _install_fake_backends(monkeypatch, fake_r2=fake_r2, writer=writer)

    exit_code = main(["--run-dir", str(run_dir)])
    payload = _read_stdout_json(capsys)

    assert exit_code == 0
    assert payload.get("mode") == "execute"
    assert _snapshot_stats(payload) == [
        {
            "run_dir": "execute-status-run",
            "status": "in_progress",
            "generated_cells": 1,
            "planned_cells": 2,
        }
    ]

    assert len(writer.payloads) == 1
    assert writer.payloads[0]["status"] == "in_progress"
    assert writer.payloads[0]["generated_cells"] == 1

    current_body = fake_r2.body_for("runs/execute-status-run/view/current.json")
    assert current_body is not None
    current_manifest = json.loads(current_body.decode("utf-8"))
    assert current_manifest["status"] == "in_progress"
    assert current_manifest["generated_cells"] == 1


def test_complete_flag_republishes_current_manifest_without_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_png(tmp_path / "complete-rerun/images/x0-y0.png")
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="complete-rerun",
        metadata_records=[
            _success_record(x_index=0, y_index=0, image_path="images/x0-y0.png")
        ],
    )
    fake_r2 = _FakeR2Client()
    writer = _CapturingSupabaseWriter()
    _install_fake_backends(monkeypatch, fake_r2=fake_r2, writer=writer)

    assert main(["--run-dir", str(run_dir)]) == 0
    _ = _read_stdout_json(capsys)
    uploads_after_first = fake_r2.upload_calls

    # 内容没变但状态收口：同一 release 也必须刷新当前指针，且不需要 -F。
    assert main(["--complete", "--run-dir", str(run_dir)]) == 0
    payload = _read_stdout_json(capsys)

    assert payload.get("mode") == "execute"
    assert _snapshot_stats(payload) == [
        {
            "run_dir": "complete-rerun",
            "status": "complete",
            "generated_cells": 1,
            "planned_cells": 2,
        }
    ]
    assert fake_r2.upload_calls > uploads_after_first
    assert writer.payloads[-1]["status"] == "complete"
    current_body = fake_r2.body_for("runs/complete-rerun/view/current.json")
    assert current_body is not None
    assert json.loads(current_body.decode("utf-8"))["status"] == "complete"


def test_missing_remote_status_is_treated_as_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_png(tmp_path / "legacy-pointer-run/images/x0-y0.png")
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="legacy-pointer-run",
        metadata_records=[
            _success_record(x_index=0, y_index=0, image_path="images/x0-y0.png")
        ],
    )
    fake_r2 = _FakeR2Client()
    writer = _CapturingSupabaseWriter()
    _install_fake_backends(monkeypatch, fake_r2=fake_r2, writer=writer)

    # 历史快照缺少 status 字段：按已完结处理并保持单调。
    legacy_pointer = {
        "schema_version": 2,
        "run_dir": "legacy-pointer-run",
        "release_id": "deadbeefdeadbeefdead",
        "bootstrap_sfw_key": (
            "runs/legacy-pointer-run/view/v2/deadbeefdeadbeefdead/bootstrap.sfw.json"
        ),
        "public_row_prefix": (
            "runs/legacy-pointer-run/view/v2/deadbeefdeadbeefdead/rows/public/"
        ),
    }
    fake_r2.seed_object(
        "dummy-public",
        "runs/legacy-pointer-run/view/current.json",
        json.dumps(legacy_pointer, ensure_ascii=False).encode("utf-8"),
    )

    assert main(["-F", "--run-dir", str(run_dir)]) == 0
    payload = _read_stdout_json(capsys)

    assert payload.get("mode") == "execute"
    assert _snapshot_stats(payload)[0]["status"] == "complete"
    assert writer.payloads[-1]["status"] == "complete"
    current_body = fake_r2.body_for("runs/legacy-pointer-run/view/current.json")
    assert current_body is not None
    assert json.loads(current_body.decode("utf-8"))["status"] == "complete"


def test_published_status_never_regresses_after_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_png(tmp_path / "monotonic-run/images/x0-y0.png")
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="monotonic-run",
        metadata_records=[
            _success_record(x_index=0, y_index=0, image_path="images/x0-y0.png")
        ],
    )
    fake_r2 = _FakeR2Client()
    writer = _CapturingSupabaseWriter()
    _install_fake_backends(monkeypatch, fake_r2=fake_r2, writer=writer)

    # 先以 complete 状态发布（人工收口），再用缺格的新快照显式强推。
    assert main(["--complete", "--run-dir", str(run_dir)]) == 0
    _ = _read_stdout_json(capsys)
    assert fake_r2.upload_calls > 0

    # 替换图片内容触发新 release；快照仍只有 1/2 格。
    _write_png(run_dir / "images/x0-y0.png", size=(12, 10))

    assert main(["-F", "--run-dir", str(run_dir)]) == 0
    payload = _read_stdout_json(capsys)

    assert payload.get("mode") == "execute"
    assert _snapshot_stats(payload)[0]["status"] == "complete"
    assert writer.payloads[-1]["status"] == "complete"
    current_body = fake_r2.body_for("runs/monotonic-run/view/current.json")
    assert current_body is not None
    assert json.loads(current_body.decode("utf-8"))["status"] == "complete"
