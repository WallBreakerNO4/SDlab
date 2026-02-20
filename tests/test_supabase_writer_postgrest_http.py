# pyright: basic, reportMissingImports=false

from __future__ import annotations

import builtins
import io
import json
import sys
from collections.abc import Mapping, Sequence
from email.message import Message
from pathlib import Path
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.supabase_writer import (
    SupabaseRemoteError,
    SupabaseWriter,
    _default_client_factory,
)


class _FakeHTTPResponse:
    def __init__(self, payload: object) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        _ = exc_type
        _ = exc
        _ = tb


def _headers(request: urllib_request.Request) -> dict[str, str]:
    return {key.lower(): value for key, value in request.header_items()}


def test_postgrest_http_client_builds_upsert_and_select_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[urllib_request.Request] = []

    def fake_urlopen(request: urllib_request.Request) -> _FakeHTTPResponse:
        captured.append(request)
        if request.get_method() == "POST":
            return _FakeHTTPResponse([{"id": "run-1"}])
        if request.get_method() == "GET":
            return _FakeHTTPResponse([{"id": "run-1"}])
        raise AssertionError("unexpected HTTP method")

    monkeypatch.setattr(urllib_request, "urlopen", fake_urlopen)

    client = _default_client_factory(
        "https://demo-project.supabase.co/",
        "service-role-key",
    )
    upsert_data = (
        client.table("runs")
        .upsert({"run_dir": "run-1"}, on_conflict="run_dir")
        .execute()
        .data
    )
    select_data = (
        client.table("runs").select("id").eq("run_dir", "run-1").limit(1).execute().data
    )

    assert upsert_data == [{"id": "run-1"}]
    assert select_data == [{"id": "run-1"}]
    assert len(captured) == 2

    post_request = captured[0]
    assert post_request.get_method() == "POST"
    post_url = urllib_parse.urlparse(post_request.full_url)
    assert post_url.path == "/rest/v1/runs"
    post_qs = urllib_parse.parse_qs(post_url.query)
    assert post_qs["on_conflict"] == ["run_dir"]
    post_headers = _headers(post_request)
    assert post_headers["apikey"] == "service-role-key"
    assert post_headers["authorization"] == "Bearer service-role-key"
    assert (
        post_headers["prefer"] == "resolution=merge-duplicates, return=representation"
    )
    assert post_headers["content-type"] == "application/json"
    post_body = post_request.data
    assert isinstance(post_body, bytes)
    assert json.loads(post_body.decode("utf-8")) == [{"run_dir": "run-1"}]

    get_request = captured[1]
    assert get_request.get_method() == "GET"
    get_url = urllib_parse.urlparse(get_request.full_url)
    assert get_url.path == "/rest/v1/runs"
    get_qs = urllib_parse.parse_qs(get_url.query)
    assert get_qs["select"] == ["id"]
    assert get_qs["run_dir"] == ["eq.run-1"]
    assert get_qs["limit"] == ["1"]
    get_headers = _headers(get_request)
    assert get_headers["apikey"] == "service-role-key"
    assert get_headers["authorization"] == "Bearer service-role-key"


def test_from_env_execute_mode_does_not_import_supabase_or_httpx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://demo-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")

    def fake_urlopen(request: urllib_request.Request) -> _FakeHTTPResponse:
        _ = request
        return _FakeHTTPResponse([{"id": "run-1"}])

    monkeypatch.setattr(urllib_request, "urlopen", fake_urlopen)

    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> object:
        if name.startswith("supabase") or name.startswith("httpx"):
            raise AssertionError(f"unexpected import: {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    writer = SupabaseWriter.from_env(dry_run=False)
    writer.upsert_upload_index(
        {
            "run_dir": "run-1",
            "run_json": {"base_seed": 1},
            "images": [],
        }
    )

    assert writer.dry_run is False


def test_postgrest_http_error_code_is_mapped_without_secret_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_url = "https://private-project.supabase.co"
    secret_key = "service-role-super-secret"
    monkeypatch.setenv("SUPABASE_URL", secret_url)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", secret_key)

    def fake_urlopen(request: urllib_request.Request) -> _FakeHTTPResponse:
        raise urllib_error.HTTPError(
            url=request.full_url,
            code=409,
            msg="conflict",
            hdrs=Message(),
            fp=io.BytesIO(
                b'{"code":"23505","message":"duplicate key SUPER_SECRET_TOKEN_123"}'
            ),
        )

    monkeypatch.setattr(urllib_request, "urlopen", fake_urlopen)

    writer = SupabaseWriter.from_env(dry_run=False)
    with pytest.raises(SupabaseRemoteError) as exc:
        writer.upsert_upload_index(
            {
                "run_dir": "run-1",
                "run_json": {"base_seed": 1},
                "images": [],
            }
        )

    assert exc.value.code == "request_failed"
    assert exc.value.context["remote_code"] == "23505"
    assert "SUPER_SECRET_TOKEN_123" not in str(exc.value)
    assert secret_url not in str(exc.value)
    assert secret_key not in str(exc.value)
