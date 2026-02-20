# pyright: basic, reportMissingImports=false, reportUnknownVariableType=false

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.upload_images_to_r2 import main

_RUN_FLAG = "SDSL_RUN_LOCAL_SUPABASE_INTEGRATION"
_RUN_DIR_ARG = "tests/fixtures/run_minimal"
_RUN_DIR_NAME = "run-20260221T160000Z"


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


def _query_counts(client: object) -> tuple[int, int, int]:
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

    images_response = (
        typed_client.table("images").select("id").eq("run_id", run_id).execute()
    )
    image_rows = getattr(images_response, "data", None)
    assert isinstance(image_rows, list)
    assert len(image_rows) >= 1

    image_ids: list[str] = []
    for image_row in image_rows:
        assert isinstance(image_row, dict)
        image_id = image_row.get("id")
        assert isinstance(image_id, str) and image_id
        image_ids.append(image_id)

    variant_count = 0
    for image_id in image_ids:
        variants_response = (
            typed_client.table("image_variants")
            .select("id")
            .eq("image_id", image_id)
            .execute()
        )
        variant_rows = getattr(variants_response, "data", None)
        assert isinstance(variant_rows, list)
        variant_count += len(variant_rows)

    return len(run_rows), len(image_rows), variant_count


def test_local_supabase_integration_with_fake_r2_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if os.getenv(_RUN_FLAG) != "1":
        pytest.skip(f"仅在 {_RUN_FLAG}=1 时运行本地 Supabase 集成回归。")

    supabase_url, service_role_key = _require_local_supabase_env()

    from scripts.r2_upload.supabase_writer import _default_client_factory

    supabase_client = _default_client_factory(supabase_url, service_role_key)

    fake_r2 = _FakeR2Client()
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "itest-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "itest-private")
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )

    first_exit = main(["--run-dir", _RUN_DIR_ARG])
    first_payload = _read_stdout_json(capsys)
    assert first_exit == 0
    assert first_payload.get("mode") == "execute"

    first_run_count, first_image_count, first_variant_count = _query_counts(
        supabase_client
    )
    assert first_run_count == 1
    assert first_image_count >= 1
    assert first_variant_count >= 1

    uploaded_after_first = fake_r2.upload_calls

    second_exit = main(["--run-dir", _RUN_DIR_ARG])
    second_payload = _read_stdout_json(capsys)
    assert second_exit == 0
    assert second_payload.get("mode") == "execute"

    second_run_count, second_image_count, second_variant_count = _query_counts(
        supabase_client
    )
    assert (second_run_count, second_image_count, second_variant_count) == (
        first_run_count,
        first_image_count,
        first_variant_count,
    )
    assert fake_r2.upload_calls == uploaded_after_first
