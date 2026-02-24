from __future__ import annotations

import http.client
import json
import os
import threading
import time
from collections.abc import Mapping
from typing import Protocol, cast
from urllib import parse as urllib_parse


class _SupabaseHTTPResponse:
    data: object

    def __init__(self, data: object) -> None:
        self.data = data


class _PostgrestHTTPError(RuntimeError):
    code: str | None
    status: int | None

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class _PostgrestHTTPQuery:
    _client: _PostgrestHTTPClient
    _table_name: str
    _mode: str | None
    _upsert_rows: list[Mapping[str, object]]
    _on_conflict: str
    _select_columns: str
    _upsert_select_columns: str | None
    _returning_mode: str
    _filters: list[tuple[str, object]]
    _limit: int | None

    def __init__(self, client: "_PostgrestHTTPClient", table_name: str) -> None:
        self._client = client
        self._table_name = table_name
        self._mode = None
        self._upsert_rows = []
        self._on_conflict = ""
        self._select_columns = "*"
        self._upsert_select_columns = None
        self._returning_mode = "representation"
        self._filters = []
        self._limit = None

    def upsert(self, json: object, *, on_conflict: str) -> "_PostgrestHTTPQuery":
        rows: list[Mapping[str, object]] = []
        if isinstance(json, Mapping):
            rows = [cast(Mapping[str, object], json)]
        elif isinstance(json, list):
            for item in cast(list[object], json):
                if not isinstance(item, Mapping):
                    raise TypeError("upsert payload rows must be JSON objects")
                rows.append(cast(Mapping[str, object], item))
            if not rows:
                raise TypeError("upsert payload must not be empty")
        else:
            raise TypeError("upsert payload must be a JSON object or array")
        self._mode = "upsert"
        self._upsert_rows = rows
        self._on_conflict = on_conflict
        return self

    def select(self, columns: str) -> "_PostgrestHTTPQuery":
        if self._mode == "upsert":
            self._upsert_select_columns = columns
            return self
        self._mode = "select"
        self._select_columns = columns
        return self

    def returning(self, mode: str) -> "_PostgrestHTTPQuery":
        normalized = mode.strip().lower()
        if normalized not in {"representation", "minimal"}:
            raise ValueError("returning mode must be 'representation' or 'minimal'")
        self._returning_mode = normalized
        return self

    def eq(self, column: str, value: object) -> "_PostgrestHTTPQuery":
        self._filters.append((column, value))
        return self

    def limit(self, size: int) -> "_PostgrestHTTPQuery":
        self._limit = size
        return self

    def execute(self) -> _SupabaseHTTPResponse:
        if self._mode == "upsert":
            if not self._upsert_rows:
                raise _PostgrestHTTPError("upsert payload is not set")
            upsert_query_params: list[tuple[str, str]] = [
                ("on_conflict", self._on_conflict)
            ]
            if self._upsert_select_columns is not None:
                upsert_query_params.append(("select", self._upsert_select_columns))
            data = self._client.request_json(
                method="POST",
                table_name=self._table_name,
                query_params=tuple(upsert_query_params),
                body=[dict(row) for row in self._upsert_rows],
                extra_headers={
                    "Prefer": f"resolution=merge-duplicates, return={self._returning_mode}"
                },
            )
            return _SupabaseHTTPResponse(data)

        if self._mode == "select":
            query_params: list[tuple[str, str]] = [("select", self._select_columns)]
            for key, value in self._filters:
                query_params.append((key, _to_postgrest_eq_filter(value)))
            if self._limit is not None:
                query_params.append(("limit", str(self._limit)))
            data = self._client.request_json(
                method="GET",
                table_name=self._table_name,
                query_params=tuple(query_params),
                body=None,
                extra_headers={},
            )
            return _SupabaseHTTPResponse(data)

        raise _PostgrestHTTPError("query mode is not set")


class _PostgrestHTTPClient:
    _rest_base_url: str
    _service_role_key: str
    _scheme: str
    _netloc: str
    _rest_base_path: str
    _timeout_s: float
    _retry_count: int
    _thread_local: threading.local

    def __init__(self, supabase_url: str, service_role_key: str) -> None:
        self._rest_base_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._service_role_key = service_role_key
        parsed = urllib_parse.urlsplit(self._rest_base_url)
        scheme = parsed.scheme.strip().lower()
        if scheme not in {"https", "http"}:
            raise _PostgrestHTTPError("failed to initialize supabase client")
        netloc = parsed.netloc.strip()
        if not netloc:
            raise _PostgrestHTTPError("failed to initialize supabase client")
        rest_base_path = parsed.path or "/"
        if not rest_base_path.startswith("/"):
            rest_base_path = f"/{rest_base_path}"
        self._scheme = scheme
        self._netloc = netloc
        self._rest_base_path = rest_base_path.rstrip("/")
        self._timeout_s = _optional_env_float("SUPABASE_HTTP_TIMEOUT_S", default=30.0)
        self._retry_count = _optional_env_int("SUPABASE_HTTP_RETRIES", default=2)
        if self._retry_count < 0:
            raise _PostgrestHTTPError("invalid supabase configuration")
        self._thread_local = threading.local()

    def table(self, table_name: str) -> _PostgrestHTTPQuery:
        return _PostgrestHTTPQuery(self, table_name)

    def request_json(
        self,
        *,
        method: str,
        table_name: str,
        query_params: tuple[tuple[str, str], ...],
        body: object | None,
        extra_headers: Mapping[str, str],
    ) -> object:
        path = _build_postgrest_path(self._rest_base_path, table_name, query_params)
        request_body: bytes | None = None
        headers = {
            "apikey": self._service_role_key,
            "Authorization": f"Bearer {self._service_role_key}",
            "Accept": "application/json",
            **dict(extra_headers),
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
            request_body = json.dumps(body, separators=(",", ":")).encode("utf-8")

        attempts = self._retry_count + 1
        last_error: _PostgrestHTTPError | None = None

        for attempt in range(attempts):
            connection = self._get_connection()
            try:
                connection.request(
                    method=method, url=path, body=request_body, headers=headers
                )
                response = connection.getresponse()
                raw = response.read()
                if response.status >= 400:
                    code = _extract_postgrest_error_code_from_raw(raw)
                    http_error = _PostgrestHTTPError(
                        "postgrest request failed",
                        code=code,
                        status=response.status,
                    )
                    if (
                        response.status in {408, 409, 425, 429, 500, 502, 503, 504}
                        and attempt + 1 < attempts
                    ):
                        self._reset_connection()
                        time.sleep(_retry_backoff_seconds(attempt))
                        continue
                    raise http_error
                return _parse_postgrest_json(raw)
            except _PostgrestHTTPError as exc:
                last_error = exc
                break
            except (http.client.HTTPException, OSError) as exc:
                self._reset_connection()
                last_error = _PostgrestHTTPError("postgrest request failed")
                if attempt + 1 < attempts:
                    time.sleep(_retry_backoff_seconds(attempt))
                    continue
                raise last_error from exc

        if last_error is not None:
            raise last_error
        raise _PostgrestHTTPError("postgrest request failed")

    def _get_connection(self) -> http.client.HTTPConnection:
        existing = getattr(self._thread_local, "connection", None)
        if isinstance(existing, http.client.HTTPConnection):
            return existing

        if self._scheme == "https":
            connection = http.client.HTTPSConnection(
                host=self._netloc,
                timeout=self._timeout_s,
            )
        else:
            connection = http.client.HTTPConnection(
                host=self._netloc,
                timeout=self._timeout_s,
            )
        self._thread_local.connection = connection
        return connection

    def _reset_connection(self) -> None:
        existing = getattr(self._thread_local, "connection", None)
        if isinstance(existing, http.client.HTTPConnection):
            try:
                existing.close()
            except Exception:
                pass
        self._thread_local.connection = None


class _ResponseReadBytesLike(Protocol):
    def __enter__(self) -> "_ResponseReadBytesLike": ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool | None: ...

    def read(self) -> bytes: ...


def _build_postgrest_path(
    rest_base_path: str,
    table_name: str,
    query_params: tuple[tuple[str, str], ...],
) -> str:
    encoded_table = urllib_parse.quote(table_name, safe="")
    base = f"{rest_base_path}/{encoded_table}"
    if not query_params:
        return base
    return f"{base}?{urllib_parse.urlencode(query_params)}"


def _parse_postgrest_json(raw: bytes) -> object:
    if not raw:
        return []
    try:
        decoded = raw.decode("utf-8")
        return cast(object, json.loads(decoded))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _PostgrestHTTPError("invalid postgrest response") from exc


def _extract_postgrest_error_code_from_raw(raw: bytes) -> str | None:
    try:
        payload = _parse_postgrest_json(raw)
    except Exception:
        return None
    if not isinstance(payload, Mapping):
        return None
    payload_map = cast(Mapping[str, object], payload)
    code = payload_map.get("code")
    if isinstance(code, str) and code.strip():
        return code.strip()
    return None


def _retry_backoff_seconds(attempt: int) -> float:
    multiplier = float(1 << attempt)
    return min(1.0, 0.2 * multiplier)


def _to_postgrest_eq_filter(value: object) -> str:
    if isinstance(value, bool):
        encoded = "true" if value else "false"
    else:
        encoded = str(value)
    return f"eq.{encoded}"


def _optional_env_int(name: str, *, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise _PostgrestHTTPError("invalid supabase configuration") from exc


def _optional_env_float(name: str, *, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise _PostgrestHTTPError("invalid supabase configuration") from exc
