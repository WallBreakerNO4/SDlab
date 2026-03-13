# pyright: basic, reportMissingImports=false

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.supabase_writer import (
    SupabaseArgumentError,
    SupabaseConfigError,
    SupabaseRemoteError,
    SupabaseWriter,
    _normalize_rows_for_postgrest,
)


def _sample_payload() -> dict[str, object]:
    return {
        "run_dir": "test-run",
        "run_json": {"base_seed": 123, "count": 1},
        "run_id": "test-run",
        "x_columns": [],
        "y_indexes": [],
        "x_count": 0,
        "y_count": 0,
        "total_cells": 0,
        "model_name": None,
        "model_description_zh": None,
        "model_description_en": None,
        "model_homepage": None,
        "model_huggingface": None,
        "model_civitai": None,
        "images": [
            {
                "x_index": 0,
                "y_index": 0,
                "batch_index": 0,
                "category": "normal",
                "width": 512,
                "height": 512,
                "blurhash": "L5H2EC=PM+yV0g-mq.wG9c010J}I",
                "metadata": {"prompt": "a test image"},
                "variants": [
                    {
                        "variant": "display_webp",
                        "bucket": "public",
                        "r2_key": "runs/r/display.webp",
                        "content_type": "image/webp",
                        "byte_size": 123,
                        "sha256": "abc",
                        "width": 512,
                        "height": 512,
                        "webp_quality": 93,
                        "avif_quality": None,
                        "avif_speed": None,
                    },
                    {
                        "variant": "thumb_webp",
                        "bucket": "public",
                        "r2_key": "runs/r/thumb.webp",
                        "content_type": "image/webp",
                        "byte_size": 64,
                        "sha256": "def",
                        "width": 256,
                        "height": 256,
                        "webp_quality": 82,
                    },
                ],
            }
        ],
    }


class _FakeResponse:
    def __init__(self, data: object) -> None:
        self.data = data


class _InMemorySupabaseClient:
    def __init__(self, *, return_upsert_rows: bool) -> None:
        self.return_upsert_rows = return_upsert_rows
        self.upsert_calls: list[dict[str, object]] = []
        self.select_execute_calls = 0
        self._tables: dict[str, dict[tuple[object, ...], dict[str, object]]] = {
            "runs": {},
            "images": {},
            "image_variants": {},
        }
        self._next_id = {"runs": 1, "images": 1, "image_variants": 1}

    def table(self, table_name: str) -> "_InMemoryQuery":
        return _InMemoryQuery(self, table_name)

    def row_count(self, table_name: str) -> int:
        return len(self._tables[table_name])

    def _upsert_many(
        self, table_name: str, rows: list[dict[str, object]], on_conflict: str
    ) -> object:
        result_rows: list[dict[str, object]] = []
        for row in rows:
            result_rows.append(self._upsert_one(table_name, row, on_conflict))
        if self.return_upsert_rows:
            return result_rows
        return []

    def _upsert_one(
        self, table_name: str, row: dict[str, object], on_conflict: str
    ) -> dict[str, object]:
        key_columns = tuple(part.strip() for part in on_conflict.split(","))
        unique_key = tuple(row[column] for column in key_columns)
        table = self._tables[table_name]

        existing = table.get(unique_key)
        if existing is None:
            row_id = f"{table_name}-{self._next_id[table_name]}"
            self._next_id[table_name] += 1
            merged = {**row, "id": row_id}
        else:
            merged = {**existing, **row, "id": existing["id"]}

        table[unique_key] = merged
        self.upsert_calls.append(
            {
                "table": table_name,
                "on_conflict": on_conflict,
                "row": dict(row),
            }
        )
        return dict(merged)

    def _select(
        self,
        table_name: str,
        filters: tuple[tuple[str, object], ...],
        limit: int | None,
    ) -> object:
        self.select_execute_calls += 1
        rows = list(self._tables[table_name].values())
        matched: list[dict[str, object]] = []
        for row in rows:
            ok = True
            for key, value in filters:
                if row.get(key) != value:
                    ok = False
                    break
            if ok:
                matched.append({"id": row["id"]})

        if limit is not None:
            return matched[:limit]
        return matched


class _InMemoryQuery:
    def __init__(self, client: _InMemorySupabaseClient, table_name: str) -> None:
        self._client = client
        self._table_name = table_name
        self._mode: str | None = None
        self._upsert_rows: list[dict[str, object]] = []
        self._on_conflict = ""
        self._filters: list[tuple[str, object]] = []
        self._limit: int | None = None

    def upsert(self, json: object, *, on_conflict: str) -> "_InMemoryQuery":
        rows: list[dict[str, object]] = []
        if isinstance(json, dict):
            rows = [dict(cast(dict[str, object], json))]
        elif isinstance(json, list):
            for item in cast(list[object], json):
                if not isinstance(item, dict):
                    raise TypeError("upsert payload rows must be dict")
                rows.append(dict(cast(dict[str, object], item)))
        else:
            raise TypeError("upsert payload must be dict or list")
        if not rows:
            raise TypeError("upsert payload must not be empty")
        self._mode = "upsert"
        self._upsert_rows = rows
        self._on_conflict = on_conflict
        return self

    def select(self, columns: str) -> "_InMemoryQuery":
        _ = columns
        if self._mode == "upsert":
            return self
        self._mode = "select"
        return self

    def eq(self, column: str, value: object) -> "_InMemoryQuery":
        self._filters.append((column, value))
        return self

    def limit(self, size: int) -> "_InMemoryQuery":
        self._limit = size
        return self

    def returning(self, mode: str) -> "_InMemoryQuery":
        _ = mode
        return self

    def execute(self) -> _FakeResponse:
        if self._mode == "upsert":
            assert self._upsert_rows
            data = self._client._upsert_many(
                self._table_name,
                self._upsert_rows,
                self._on_conflict,
            )
            return _FakeResponse(data)

        if self._mode == "select":
            data = self._client._select(
                self._table_name,
                tuple(self._filters),
                self._limit,
            )
            return _FakeResponse(data)

        raise AssertionError("query mode is not set")


class _BoomError(RuntimeError):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


class _BoomQuery:
    def upsert(self, json: object, *, on_conflict: str) -> "_BoomQuery":
        _ = json
        _ = on_conflict
        return self

    def select(self, columns: str) -> "_BoomQuery":
        _ = columns
        return self

    def eq(self, column: str, value: object) -> "_BoomQuery":
        _ = column
        _ = value
        return self

    def limit(self, size: int) -> "_BoomQuery":
        _ = size
        return self

    def returning(self, mode: str) -> "_BoomQuery":
        _ = mode
        return self

    def execute(self) -> _FakeResponse:
        raise _BoomError("db exploded: SUPER_SECRET_TOKEN_123", code="23505")


class _BoomClient:
    def table(self, table_name: str) -> _BoomQuery:
        _ = table_name
        return _BoomQuery()


def test_from_env_dry_run_does_not_require_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    def fail_factory(url: str, key: str) -> _InMemorySupabaseClient:
        _ = url
        _ = key
        raise AssertionError("dry-run must not initialize client")

    writer = SupabaseWriter.from_env(dry_run=True, client_factory=fail_factory)

    assert writer.dry_run is True


def test_from_env_missing_required_env_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    with pytest.raises(SupabaseConfigError) as exc:
        _ = SupabaseWriter.from_env(dry_run=False)

    assert exc.value.category == "config"
    assert exc.value.code == "missing_env"
    assert exc.value.context["missing_env"] == "SUPABASE_URL"


def test_from_env_factory_error_redacts_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_url = "https://private.example.supabase.co"
    secret_key = "service-role-super-secret"
    monkeypatch.setenv("SUPABASE_URL", secret_url)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", secret_key)

    def broken_factory(url: str, key: str) -> _InMemorySupabaseClient:
        raise RuntimeError(f"connect failed {url} {key}")

    with pytest.raises(SupabaseConfigError) as exc:
        _ = SupabaseWriter.from_env(dry_run=False, client_factory=broken_factory)

    assert exc.value.code == "client_init_failed"
    assert secret_url not in str(exc.value)
    assert secret_key not in str(exc.value)


def test_upsert_upload_index_dry_run_skips_client_calls() -> None:
    class FailClient:
        def table(self, table_name: str) -> _InMemoryQuery:
            _ = table_name
            raise AssertionError("dry-run should not access client")

    writer = SupabaseWriter(client=FailClient(), dry_run=True)
    writer.upsert_upload_index(_sample_payload())


def test_upsert_upload_index_is_idempotent() -> None:
    client = _InMemorySupabaseClient(return_upsert_rows=True)
    writer = SupabaseWriter(client=client, dry_run=False)
    payload = _sample_payload()

    writer.upsert_upload_index(payload)
    writer.upsert_upload_index(payload)

    assert client.row_count("runs") == 1
    assert client.row_count("images") == 1
    assert client.row_count("image_variants") == 2

    on_conflicts = {str(call["on_conflict"]) for call in client.upsert_calls}
    assert "run_dir" in on_conflicts
    assert "run_id,x_index,y_index,batch_index" in on_conflicts
    assert "image_id,variant" in on_conflicts


def test_upsert_upload_index_extracts_structured_columns() -> None:
    client = _InMemorySupabaseClient(return_upsert_rows=True)
    writer = SupabaseWriter(client=client, dry_run=False)
    payload = {
        "run_dir": "structured-run",
        "run_json": {
            "run_id": "json-run-id",
            "selection": {"x_count": 99, "y_count": 99, "total_cells": 9801},
        },
        "run_id": "structured-run-id",
        "x_columns": [{"type": "quality", "description": {"zh": "高质量"}}],
        "y_indexes": [0, 1],
        "x_count": 1,
        "y_count": 2,
        "total_cells": 2,
        "model_name": "ChenkinNoob XL Rectified Flow",
        "model_description_zh": "示例配置",
        "model_description_en": "Example config",
        "model_homepage": None,
        "model_huggingface": "https://huggingface.co/example",
        "model_civitai": None,
        "images": [
            {
                "x_index": 0,
                "y_index": 1,
                "batch_index": 0,
                "category": "normal",
                "metadata": {
                    "seed": 42,
                    "prompt_hash": "hash-1",
                    "positive_prompt": "hello",
                    "y_value": "Y1",
                },
                "variants": [],
            }
        ],
    }

    writer.upsert_upload_index(cast(dict[str, object], payload))

    run_row = next(iter(client._tables["runs"].values()))
    assert run_row["run_id"] == "structured-run-id"
    assert run_row["x_count"] == 1
    assert run_row["y_count"] == 2
    assert run_row["total_cells"] == 2
    assert run_row["y_indexes"] == [0, 1]
    assert run_row["x_columns"] == [
        {"type": "quality", "description": {"zh": "高质量"}}
    ]
    assert run_row["model_name"] == "ChenkinNoob XL Rectified Flow"
    assert run_row["model_description_zh"] == "示例配置"
    assert run_row["model_description_en"] == "Example config"
    assert run_row["model_huggingface"] == "https://huggingface.co/example"

    image_row = next(iter(client._tables["images"].values()))
    assert image_row["seed"] == "42"
    assert image_row["prompt_hash"] == "hash-1"
    assert image_row["positive_prompt"] == "hello"
    assert image_row["y_value"] == "Y1"


def test_upsert_upload_index_fallbacks_to_select_for_ids() -> None:
    client = _InMemorySupabaseClient(return_upsert_rows=False)
    writer = SupabaseWriter(client=client, dry_run=False)

    writer.upsert_upload_index(_sample_payload())

    assert client.row_count("runs") == 1
    assert client.row_count("images") == 1
    assert client.row_count("image_variants") == 2
    assert client.select_execute_calls >= 2


def test_upsert_upload_index_preserves_large_seed_as_string() -> None:
    client = _InMemorySupabaseClient(return_upsert_rows=True)
    writer = SupabaseWriter(client=client, dry_run=False)
    payload = {
        "run_dir": "large-seed-run",
        "run_json": {"run_id": "large-seed-run"},
        "run_id": "large-seed-run",
        "x_columns": [],
        "y_indexes": [],
        "x_count": 0,
        "y_count": 0,
        "total_cells": 0,
        "model_name": None,
        "model_description_zh": None,
        "model_description_en": None,
        "model_homepage": None,
        "model_huggingface": None,
        "model_civitai": None,
        "images": [
            {
                "x_index": 0,
                "y_index": 0,
                "batch_index": 0,
                "category": "normal",
                "metadata": {"seed": 18020657621215222860},
                "variants": [],
            }
        ],
    }

    writer.upsert_upload_index(cast(dict[str, object], payload))

    image_row = next(iter(client._tables["images"].values()))
    assert image_row["seed"] == "18020657621215222860"


def test_upsert_upload_index_requires_structured_run_fields() -> None:
    client = _InMemorySupabaseClient(return_upsert_rows=True)
    writer = SupabaseWriter(client=client, dry_run=False)
    payload = {
        "run_dir": "missing-structured-run",
        "run_json": {
            "run_id": "json-only-run-id",
            "selection": {
                "x_columns": [{"type": "quality"}],
                "y_indexes": [0],
                "x_count": 1,
                "y_count": 1,
                "total_cells": 1,
            },
        },
        "x_columns": [],
        "y_indexes": [],
        "x_count": 0,
        "y_count": 0,
        "total_cells": 0,
        "images": [],
    }

    with pytest.raises(SupabaseArgumentError) as exc:
        writer.upsert_upload_index(cast(dict[str, object], payload))

    assert exc.value.code == "invalid_payload"
    assert exc.value.context["field"] == "run_id"


def test_upsert_upload_index_rejects_invalid_payload() -> None:
    writer = SupabaseWriter(client=None, dry_run=True)
    bad_payload = {
        "run_dir": "invalid-payload-run",
        "run_json": {},
        "images": "not-an-array",
    }

    with pytest.raises(SupabaseArgumentError) as exc:
        writer.upsert_upload_index(cast(dict[str, object], bad_payload))

    assert exc.value.code == "invalid_payload"
    assert exc.value.context["field"] == "images"


def test_remote_error_wraps_without_secret_leak() -> None:
    writer = SupabaseWriter(client=_BoomClient(), dry_run=False)

    with pytest.raises(SupabaseRemoteError) as exc:
        writer.upsert_upload_index(_sample_payload())

    assert exc.value.code == "request_failed"
    assert exc.value.context["table"] == "runs"
    assert exc.value.context["operation"] == "upsert"
    assert exc.value.context["remote_code"] == "23505"
    assert "SUPER_SECRET_TOKEN_123" not in str(exc.value)


def test_normalize_rows_for_postgrest_fills_missing_keys_with_null() -> None:
    rows = [
        {"image_id": "img-1", "variant": "thumb_webp", "webp_quality": 82},
        {"image_id": "img-1", "variant": "display_avif", "avif_quality": 20},
    ]

    normalized = _normalize_rows_for_postgrest(rows)

    assert len(normalized) == 2
    assert set(normalized[0].keys()) == set(normalized[1].keys())
    assert normalized[0]["avif_quality"] is None
    assert normalized[1]["webp_quality"] is None
