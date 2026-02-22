# pyright: basic, reportMissingImports=false

from __future__ import annotations

import builtins
import http.client
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib import parse as urllib_parse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.supabase_writer import (
    SupabaseRemoteError,
    SupabaseWriter,
    _default_client_factory,
)


class _FakeHTTPResponse:
    def __init__(self, payload: object, *, status: int = 200) -> None:
        self.status = status
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw


class _CapturedRequest:
    def __init__(
        self, method: str, url: str, body: bytes | None, headers: dict[str, str]
    ):
        self.method = method
        self.url = url
        self.body = body
        self.headers = headers


class _FakeConnection:
    def __init__(
        self, host: str, *, timeout: float, captured: list[_CapturedRequest]
    ) -> None:
        self.host = host
        self.timeout = timeout
        self._captured = captured
        self._last_method = ""

    def request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self._last_method = method
        self._captured.append(_CapturedRequest(method, url, body, dict(headers or {})))

    def getresponse(self) -> _FakeHTTPResponse:
        if self._last_method == "POST":
            return _FakeHTTPResponse([{"id": "run-1"}])
        if self._last_method == "GET":
            return _FakeHTTPResponse([{"id": "run-1"}])
        raise AssertionError("unexpected HTTP method")

    def close(self) -> None:
        return


def test_postgrest_http_client_builds_upsert_and_select_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[_CapturedRequest] = []

    def fake_https_connection(host: str, timeout: float = 0.0) -> _FakeConnection:
        return _FakeConnection(host, timeout=timeout, captured=captured)

    monkeypatch.setattr(http.client, "HTTPSConnection", fake_https_connection)

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
    assert post_request.method == "POST"
    post_url = urllib_parse.urlparse(
        f"https://demo-project.supabase.co{post_request.url}"
    )
    assert post_url.path == "/rest/v1/runs"
    post_qs = urllib_parse.parse_qs(post_url.query)
    assert post_qs["on_conflict"] == ["run_dir"]
    post_headers = {key.lower(): value for key, value in post_request.headers.items()}
    assert post_headers["apikey"] == "service-role-key"
    assert post_headers["authorization"] == "Bearer service-role-key"
    assert (
        post_headers["prefer"] == "resolution=merge-duplicates, return=representation"
    )
    assert post_headers["content-type"] == "application/json"
    post_body = post_request.body
    assert isinstance(post_body, bytes)
    assert json.loads(post_body.decode("utf-8")) == [{"run_dir": "run-1"}]

    get_request = captured[1]
    assert get_request.method == "GET"
    get_url = urllib_parse.urlparse(
        f"https://demo-project.supabase.co{get_request.url}"
    )
    assert get_url.path == "/rest/v1/runs"
    get_qs = urllib_parse.parse_qs(get_url.query)
    assert get_qs["select"] == ["id"]
    assert get_qs["run_dir"] == ["eq.run-1"]
    assert get_qs["limit"] == ["1"]
    get_headers = {key.lower(): value for key, value in get_request.headers.items()}
    assert get_headers["apikey"] == "service-role-key"
    assert get_headers["authorization"] == "Bearer service-role-key"


def test_from_env_execute_mode_does_not_import_supabase_or_httpx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://demo-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")

    def fake_https_connection(host: str, timeout: float = 0.0) -> _FakeConnection:
        _ = (host, timeout)
        return _FakeConnection("demo-project.supabase.co", timeout=30.0, captured=[])

    monkeypatch.setattr(http.client, "HTTPSConnection", fake_https_connection)

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
    monkeypatch.setenv("SUPABASE_HTTP_RETRIES", "0")

    class _ErrorConnection(_FakeConnection):
        def getresponse(self) -> _FakeHTTPResponse:
            return _FakeHTTPResponse(
                {"code": "23505", "message": "duplicate key SUPER_SECRET_TOKEN_123"},
                status=409,
            )

    def fake_https_connection(host: str, timeout: float = 0.0) -> _ErrorConnection:
        return _ErrorConnection(host, timeout=timeout, captured=[])

    monkeypatch.setattr(http.client, "HTTPSConnection", fake_https_connection)

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


def test_postgrest_http_retries_transient_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://demo-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_HTTP_RETRIES", "1")

    class _RetryConnection(_FakeConnection):
        request_calls = 0

        def request(
            self,
            method: str,
            url: str,
            body: bytes | None = None,
            headers: Mapping[str, str] | None = None,
        ) -> None:
            type(self).request_calls += 1
            if type(self).request_calls == 1:
                raise OSError("simulated broken pipe")
            super().request(method=method, url=url, body=body, headers=headers)

    def fake_https_connection(host: str, timeout: float = 0.0) -> _RetryConnection:
        return _RetryConnection(host, timeout=timeout, captured=[])

    monkeypatch.setattr(http.client, "HTTPSConnection", fake_https_connection)

    writer = SupabaseWriter.from_env(dry_run=False)

    writer.upsert_upload_index(
        {
            "run_dir": "run-1",
            "run_json": {"base_seed": 1},
            "images": [],
        }
    )
    assert _RetryConnection.request_calls == 2
