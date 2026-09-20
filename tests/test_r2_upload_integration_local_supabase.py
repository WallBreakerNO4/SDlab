# pyright: basic, reportMissingImports=false, reportUnknownVariableType=false

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any, cast

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.upload_images_to_r2 import main

_RUN_FLAG = "SDSL_RUN_LOCAL_SUPABASE_INTEGRATION"
_RUN_FIXTURE_DIR = ROOT / "tests/fixtures/run_minimal"
_RUN_DIR_NAME = "local-supabase-run"
_RUN_ASSETS_DIR_NAME = "local-supabase-assets-run"


class _FakeR2Client:
    def __init__(self) -> None:
        self._objects: set[tuple[str, str]] = set()
        self._object_bodies: dict[tuple[str, str], bytes] = {}
        self.upload_calls = 0

    def head_exists(self, bucket_name: str, key: str, *, bucket_scope: str) -> bool:
        _ = bucket_scope
        return (bucket_name, key) in self._objects

    def read_bytes_if_exists(
        self, bucket_name: str, key: str, *, bucket_scope: str
    ) -> bytes | None:
        _ = bucket_scope
        return self._object_bodies.get((bucket_name, key))

    def read_body(self, bucket_name: str, key: str) -> bytes | None:
        return self._object_bodies.get((bucket_name, key))

    def upload(self, plan: object) -> None:
        bucket_name = str(getattr(plan, "bucket_name"))
        key = str(getattr(plan, "key"))
        self._objects.add((bucket_name, key))
        body_bytes = getattr(plan, "body_bytes", None)
        self._object_bodies[(bucket_name, key)] = (
            body_bytes if isinstance(body_bytes, bytes) else b""
        )
        self.upload_calls += 1


def _read_stdout_json(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    output = capsys.readouterr().out.strip()
    assert output
    lines = [line for line in output.splitlines() if line.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def _require_local_supabase_env() -> tuple[str, str]:
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    if not supabase_url:
        pytest.fail("启用本地 Supabase 集成测试时必须设置 SUPABASE_URL。")
    if not (
        supabase_url.startswith("http://localhost:")
        or supabase_url.startswith("http://127.0.0.1:")
    ):
        pytest.fail(
            "启用本地 Supabase 集成测试时，SUPABASE_URL 必须指向 localhost 或 127.0.0.1。"
        )

    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not service_role_key:
        pytest.fail("启用本地 Supabase 集成测试时必须设置 SUPABASE_SERVICE_ROLE_KEY。")

    return supabase_url, service_role_key


def _prepare_run_dir(tmp_path: Path) -> Path:
    target = tmp_path / _RUN_DIR_NAME
    shutil.copytree(_RUN_FIXTURE_DIR, target)
    (target / "run.json").write_text(
        json.dumps(
            {
                "run_id": _RUN_DIR_NAME,
                "run_key": _RUN_DIR_NAME,
                "run_dir": _RUN_DIR_NAME,
                "created_at": "2026-05-01T00:00:00Z",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return target


def _query_counts(client: object) -> tuple[int, int, int, int, int]:
    typed_client = cast(Any, client)
    runs_response = (
        typed_client.table("runs").select("id").eq("run_dir", _RUN_DIR_NAME).execute()
    )
    run_rows = getattr(runs_response, "data", None)
    assert isinstance(run_rows, list)
    assert len(run_rows) == 1

    run_row = run_rows[0]
    assert isinstance(run_row, dict)
    run_id = run_row.get("id")
    assert isinstance(run_id, str) and run_id

    snapshots_response = (
        typed_client.table("run_snapshots")
        .select("run_id")
        .eq("run_id", run_id)
        .execute()
    )
    snapshot_rows = getattr(snapshots_response, "data", None)
    assert isinstance(snapshot_rows, list)
    assert len(snapshot_rows) == 1

    run_list_items_response = (
        typed_client.table("run_list_items")
        .select("run_id")
        .eq("run_id", run_id)
        .execute()
    )
    run_list_item_rows = getattr(run_list_items_response, "data", None)
    assert isinstance(run_list_item_rows, list)
    assert len(run_list_item_rows) == 1

    grid_items_response = (
        typed_client.table("run_grid_items").select("id").eq("run_id", run_id).execute()
    )
    grid_item_rows = getattr(grid_items_response, "data", None)
    assert isinstance(grid_item_rows, list)
    assert len(grid_item_rows) >= 1

    grid_cells_response = (
        typed_client.table("run_grid_cells").select("id").eq("run_id", run_id).execute()
    )
    grid_cell_rows = getattr(grid_cells_response, "data", None)
    assert isinstance(grid_cell_rows, list)
    assert len(grid_cell_rows) >= 1

    grid_snapshots_response = (
        typed_client.table("run_grid_item_snapshots")
        .select("run_id")
        .eq("run_id", run_id)
        .execute()
    )
    grid_snapshot_rows = getattr(grid_snapshots_response, "data", None)
    assert isinstance(grid_snapshot_rows, list)
    assert len(grid_snapshot_rows) >= 1

    return (
        len(run_rows),
        len(snapshot_rows),
        len(run_list_item_rows),
        len(grid_item_rows),
        len(grid_cell_rows),
    )


def test_local_supabase_integration_with_fake_r2_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if os.getenv(_RUN_FLAG) != "1":
        pytest.skip(f"仅在 {_RUN_FLAG}=1 时运行本地 Supabase 集成回归。")

    supabase_url, service_role_key = _require_local_supabase_env()

    from scripts.r2_upload.supabase_writer import _default_client_factory

    supabase_client = _default_client_factory(supabase_url, service_role_key)

    fake_r2 = _FakeR2Client()
    run_dir = _prepare_run_dir(tmp_path)
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "itest-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "itest-private")
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )

    first_exit = main(["--run-dir", str(run_dir)])
    first_payload = _read_stdout_json(capsys)
    assert first_exit == 0
    assert first_payload.get("mode") == "execute"

    (
        first_run_count,
        first_snapshot_count,
        first_run_list_count,
        first_grid_item_count,
        first_grid_cell_count,
    ) = _query_counts(supabase_client)
    assert first_run_count == 1
    assert first_snapshot_count == 1
    assert first_run_list_count == 1
    assert first_grid_item_count >= 1
    assert first_grid_cell_count >= 1

    uploaded_after_first = fake_r2.upload_calls

    second_exit = main(["--run-dir", str(run_dir)])
    second_payload = _read_stdout_json(capsys)
    assert second_exit == 0
    assert second_payload.get("mode") == "execute"

    (
        second_run_count,
        second_snapshot_count,
        second_run_list_count,
        second_grid_item_count,
        second_grid_cell_count,
    ) = _query_counts(supabase_client)
    assert (
        second_run_count,
        second_snapshot_count,
        second_run_list_count,
        second_grid_item_count,
        second_grid_cell_count,
    ) == (
        first_run_count,
        first_snapshot_count,
        first_run_list_count,
        first_grid_item_count,
        first_grid_cell_count,
    )
    assert fake_r2.upload_calls == uploaded_after_first


def _write_repo_image(path: Path, *, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color).save(path, format="JPEG")


def _prepare_run_dir_with_scanned_assets(
    tmp_path: Path,
) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo-root"
    _write_repo_image(
        repo_root / "data/models/example/image.jpg",
        color=(10, 20, 30),
    )
    _write_repo_image(
        repo_root / "data/models/example/images/card-1.jpg",
        color=(40, 50, 60),
    )

    target = tmp_path / _RUN_ASSETS_DIR_NAME
    shutil.copytree(_RUN_FIXTURE_DIR, target)
    (target / "run.json").write_text(
        json.dumps(
            {
                "run_id": _RUN_ASSETS_DIR_NAME,
                "run_key": _RUN_ASSETS_DIR_NAME,
                "run_dir": _RUN_ASSETS_DIR_NAME,
                "created_at": "2026-05-01T00:00:00Z",
                "config_path": "data/models/example/config.yaml",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return target, repo_root


def _read_run_list_assets(
    client: object, run_dir_name: str
) -> tuple[dict[str, object] | None, list[object]]:
    typed_client = cast(Any, client)
    response = (
        typed_client.table("run_list_items")
        .select("cover,homepage_cards")
        .eq("run_dir", run_dir_name)
        .execute()
    )
    rows = getattr(response, "data", None)
    assert isinstance(rows, list)
    assert len(rows) == 1

    row = rows[0]
    assert isinstance(row, dict)
    cover = row.get("cover")
    if cover is not None:
        assert isinstance(cover, dict)
    homepage_cards = row.get("homepage_cards")
    assert isinstance(homepage_cards, list)
    return cover, homepage_cards


def test_local_supabase_integration_scans_run_assets_on_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if os.getenv(_RUN_FLAG) != "1":
        pytest.skip(f"仅在 {_RUN_FLAG}=1 时运行本地 Supabase 集成回归。")

    supabase_url, service_role_key = _require_local_supabase_env()

    from scripts.r2_upload import upload_planner as upload_planner_module
    from scripts.r2_upload.supabase_writer import _default_client_factory

    supabase_client = _default_client_factory(supabase_url, service_role_key)

    fake_r2 = _FakeR2Client()
    run_dir, repo_root = _prepare_run_dir_with_scanned_assets(tmp_path)
    monkeypatch.setattr(upload_planner_module, "_REPO_ROOT", repo_root)
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "itest-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "itest-private")
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )

    first_exit = main(["--run-dir", str(run_dir)])
    first_payload = _read_stdout_json(capsys)
    assert first_exit == 0
    assert first_payload.get("mode") == "execute"
    assert first_payload.get("asset_scans") == [
        {
            "run_dir": _RUN_ASSETS_DIR_NAME,
            "cover_image": "data/models/example/image.jpg",
            "homepage_images": ["data/models/example/images/card-1.jpg"],
        }
    ]

    first_cover, first_homepage_cards = _read_run_list_assets(
        supabase_client, _RUN_ASSETS_DIR_NAME
    )
    assert first_cover is not None
    first_cover_key = first_cover.get("thumb_webp_r2_key")
    assert isinstance(first_cover_key, str) and first_cover_key
    assert len(first_homepage_cards) == 1
    uploaded_after_first = fake_r2.upload_calls

    # 生图启动后补放封面图与主页缩略图；同一 release 再次发布只更新资产类数据。
    _write_repo_image(
        repo_root / "data/models/example/image.jpg",
        color=(90, 10, 10),
    )
    _write_repo_image(
        repo_root / "data/models/example/images/card-2.jpg",
        color=(70, 80, 90),
    )

    second_exit = main(["--run-dir", str(run_dir)])
    second_payload = _read_stdout_json(capsys)
    assert second_exit == 0
    assert second_payload.get("mode") == "execute"
    assert fake_r2.upload_calls > uploaded_after_first

    second_cover, second_homepage_cards = _read_run_list_assets(
        supabase_client, _RUN_ASSETS_DIR_NAME
    )
    assert second_cover is not None
    assert second_cover.get("thumb_webp_r2_key") not in {None, first_cover_key}
    assert len(second_homepage_cards) == 2
    homepage_keys = [
        card.get("thumb_webp_r2_key")
        for card in second_homepage_cards
        if isinstance(card, dict)
    ]
    assert all(isinstance(key, str) and key for key in homepage_keys)
    assert len(set(homepage_keys)) == 2


def _prepare_run_dir_in_progress(tmp_path: Path) -> tuple[Path, str]:
    """2 个计划单元格、本次快照只有 1 格：应判定为进行中。"""
    run_dir_name = f"local-supabase-status-run-{uuid.uuid4().hex[:8]}"
    target = tmp_path / run_dir_name
    shutil.copytree(_RUN_FIXTURE_DIR, target)
    (target / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_dir_name,
                "run_key": run_dir_name,
                "run_dir": run_dir_name,
                "created_at": "2026-05-01T00:00:00Z",
                "selection": {
                    "x_columns": [
                        {"type": "normal", "description": {"zh": "列 1"}},
                        {"type": "normal", "description": {"zh": "列 2"}},
                    ],
                    "y_indexes": [0],
                    "x_count": 2,
                    "y_count": 1,
                    "total_cells": 2,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return target, run_dir_name


def _read_run_list_status(
    client: object, run_dir_name: str
) -> dict[str, object]:
    typed_client = cast(Any, client)
    response = (
        typed_client.table("run_list_items")
        .select("status,generated_cells,published_at")
        .eq("run_dir", run_dir_name)
        .execute()
    )
    rows = getattr(response, "data", None)
    assert isinstance(rows, list)
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, dict)
    return row


def _append_second_cell(run_dir: Path) -> None:
    image_path = run_dir / "images/x1-y0.png"
    Image.new("RGB", (8, 6), (90, 40, 10)).save(image_path, format="PNG")
    with (run_dir / "metadata.jsonl").open("a", encoding="utf-8") as handle:
        _ = handle.write(
            json.dumps(
                {
                    "status": "success",
                    "x_index": 1,
                    "y_index": 0,
                    "batch_index": 1,
                    "x_info_type": "normal",
                    "local_image_path": "images/x1-y0.png",
                    "positive_prompt": "second cell prompt",
                    "prompt_hash": "second-cell-prompt-hash",
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def _remove_second_cell(run_dir: Path) -> None:
    metadata_path = run_dir / "metadata.jsonl"
    kept: list[str] = []
    for line in metadata_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("x_index") == 1:
            continue
        kept.append(line)
    metadata_path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _read_current_manifest(
    fake_r2: _FakeR2Client, run_dir_name: str
) -> dict[str, object]:
    body = fake_r2.read_body(
        "itest-public", f"runs/{run_dir_name}/view/current.json"
    )
    assert body is not None
    parsed = json.loads(body.decode("utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def test_local_supabase_integration_publishes_snapshot_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if os.getenv(_RUN_FLAG) != "1":
        pytest.skip(f"仅在 {_RUN_FLAG}=1 时运行本地 Supabase 集成回归。")

    supabase_url, service_role_key = _require_local_supabase_env()

    from scripts.r2_upload.supabase_writer import _default_client_factory

    supabase_client = _default_client_factory(supabase_url, service_role_key)

    fake_r2 = _FakeR2Client()
    run_dir, run_dir_name = _prepare_run_dir_in_progress(tmp_path)
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "itest-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "itest-private")
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )

    first_exit = main(["--run-dir", str(run_dir)])
    first_payload = _read_stdout_json(capsys)
    assert first_exit == 0
    assert first_payload.get("snapshot_stats") == [
        {
            "run_dir": run_dir_name,
            "status": "in_progress",
            "generated_cells": 1,
            "planned_cells": 2,
        }
    ]

    first_row = _read_run_list_status(supabase_client, run_dir_name)
    assert first_row.get("status") == "in_progress"
    assert first_row.get("generated_cells") == 1
    first_published_at = first_row.get("published_at")
    assert isinstance(first_published_at, str) and first_published_at

    first_manifest = _read_current_manifest(fake_r2, run_dir_name)
    assert first_manifest.get("status") == "in_progress"
    assert first_manifest.get("generated_cells") == 1

    uploads_after_first = fake_r2.upload_calls

    # 内容无变化的重复发布：不重复写 R2 对象。
    second_exit = main(["--run-dir", str(run_dir)])
    assert second_exit == 0
    _ = _read_stdout_json(capsys)
    assert fake_r2.upload_calls == uploads_after_first

    # --complete 收口：同一 release 也刷新当前指针与发布时间。
    time.sleep(0.02)
    third_exit = main(["--complete", "--run-dir", str(run_dir)])
    third_payload = _read_stdout_json(capsys)
    assert third_exit == 0
    assert third_payload.get("snapshot_stats") == [
        {
            "run_dir": run_dir_name,
            "status": "complete",
            "generated_cells": 1,
            "planned_cells": 2,
        }
    ]
    assert fake_r2.upload_calls > uploads_after_first

    third_row = _read_run_list_status(supabase_client, run_dir_name)
    assert third_row.get("status") == "complete"
    assert third_row.get("generated_cells") == 1
    third_published_at = third_row.get("published_at")
    assert isinstance(third_published_at, str)
    assert third_published_at > first_published_at

    third_manifest = _read_current_manifest(fake_r2, run_dir_name)
    assert third_manifest.get("status") == "complete"
    assert third_manifest.get("generated_cells") == 1


def test_local_supabase_integration_replaces_snapshot_and_blocks_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if os.getenv(_RUN_FLAG) != "1":
        pytest.skip(f"仅在 {_RUN_FLAG}=1 时运行本地 Supabase 集成回归。")

    supabase_url, service_role_key = _require_local_supabase_env()

    from scripts.r2_upload.supabase_writer import _default_client_factory

    supabase_client = _default_client_factory(supabase_url, service_role_key)

    fake_r2 = _FakeR2Client()
    run_dir, run_dir_name = _prepare_run_dir_in_progress(tmp_path)
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "itest-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "itest-private")
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )

    assert main(["--run-dir", str(run_dir)]) == 0
    _ = _read_stdout_json(capsys)
    first_manifest = _read_current_manifest(fake_r2, run_dir_name)
    assert first_manifest["generated_cells"] == 1
    first_release_id = first_manifest["release_id"]

    # 补上第二格：格数增加，不需要 -F 自动取代网站当前快照。
    _append_second_cell(run_dir)

    second_exit = main(["--run-dir", str(run_dir)])
    second_payload = _read_stdout_json(capsys)
    assert second_exit == 0
    assert second_payload.get("snapshot_stats") == [
        {
            "run_dir": run_dir_name,
            "status": "complete",
            "generated_cells": 2,
            "planned_cells": 2,
        }
    ]
    second_manifest = _read_current_manifest(fake_r2, run_dir_name)
    assert second_manifest["release_id"] != first_release_id
    assert second_manifest["generated_cells"] == 2
    assert second_manifest["status"] == "complete"
    second_row = _read_run_list_status(supabase_client, run_dir_name)
    assert second_row.get("generated_cells") == 2
    assert second_row.get("status") == "complete"
    uploads_before_rollback = fake_r2.upload_calls

    # 回退：移除第二格 → 拒绝并要求 -F，当前快照与 R2 对象均不变。
    _remove_second_cell(run_dir)

    rollback_exit = main(["--run-dir", str(run_dir)])
    rollback_payload = _read_stdout_json(capsys)
    assert rollback_exit == 2
    assert rollback_payload.get("category") == "argument"
    assert "-F/--force-publish" in str(rollback_payload.get("message"))
    assert fake_r2.upload_calls == uploads_before_rollback
    assert _read_current_manifest(fake_r2, run_dir_name) == second_manifest

    # 显式强推：回退快照生效，已完结状态单调不回退。
    force_exit = main(["-F", "--run-dir", str(run_dir)])
    force_payload = _read_stdout_json(capsys)
    assert force_exit == 0
    assert force_payload.get("force_publish") is True
    forced_manifest = _read_current_manifest(fake_r2, run_dir_name)
    assert forced_manifest["release_id"] == first_release_id
    assert forced_manifest["generated_cells"] == 1
    assert forced_manifest["status"] == "complete"
    forced_row = _read_run_list_status(supabase_client, run_dir_name)
    assert forced_row.get("generated_cells") == 1
    assert forced_row.get("status") == "complete"
