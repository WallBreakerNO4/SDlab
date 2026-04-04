# pyright: basic, reportMissingImports=false, reportUnknownVariableType=false

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.upload_images_to_r2 import main

_RUN_FLAG = "SDSL_RUN_LOCAL_SUPABASE_INTEGRATION"
_RUN_FIXTURE_DIR = ROOT / "tests/fixtures/run_minimal"
_RUN_DIR_NAME = "local-supabase-run"


class _FakeR2Client:
    def __init__(self) -> None:
        self._objects: set[tuple[str, str]] = set()
        self.upload_calls = 0

    def head_exists(self, bucket_name: str, key: str, *, bucket_scope: str) -> bool:
        _ = bucket_scope
        return (bucket_name, key) in self._objects

    def upload(self, plan: object) -> None:
        bucket_name = str(getattr(plan, "bucket_name"))
        key = str(getattr(plan, "key"))
        self._objects.add((bucket_name, key))
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
