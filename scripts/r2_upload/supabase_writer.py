from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from typing import Protocol, cast
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

_MISSING_ENV_MESSAGE = "missing required Supabase configuration"


class SupabaseResponseLike(Protocol):
    data: object


class SupabaseQueryLike(Protocol):
    def upsert(self, json: object, *, on_conflict: str) -> "SupabaseQueryLike": ...

    def select(self, columns: str) -> "SupabaseQueryLike": ...

    def eq(self, column: str, value: object) -> "SupabaseQueryLike": ...

    def limit(self, size: int) -> "SupabaseQueryLike": ...

    def execute(self) -> SupabaseResponseLike: ...


class SupabaseClientLike(Protocol):
    def table(self, table_name: str) -> SupabaseQueryLike: ...


ClientFactory = Callable[[str, str], SupabaseClientLike]


class _SupabaseHTTPResponse:
    data: object

    def __init__(self, data: object) -> None:
        self.data = data


class _PostgrestHTTPError(RuntimeError):
    code: str | None

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class _PostgrestHTTPQuery:
    _client: _PostgrestHTTPClient
    _table_name: str
    _mode: str | None
    _upsert_json: Mapping[str, object] | None
    _on_conflict: str
    _select_columns: str
    _filters: list[tuple[str, object]]
    _limit: int | None

    def __init__(self, client: "_PostgrestHTTPClient", table_name: str) -> None:
        self._client = client
        self._table_name = table_name
        self._mode = None
        self._upsert_json = None
        self._on_conflict = ""
        self._select_columns = "*"
        self._filters = []
        self._limit = None

    def upsert(self, json: object, *, on_conflict: str) -> "_PostgrestHTTPQuery":
        if not isinstance(json, Mapping):
            raise TypeError("upsert payload must be a JSON object")
        self._mode = "upsert"
        self._upsert_json = cast(Mapping[str, object], json)
        self._on_conflict = on_conflict
        return self

    def select(self, columns: str) -> "_PostgrestHTTPQuery":
        self._mode = "select"
        self._select_columns = columns
        return self

    def eq(self, column: str, value: object) -> "_PostgrestHTTPQuery":
        self._filters.append((column, value))
        return self

    def limit(self, size: int) -> "_PostgrestHTTPQuery":
        self._limit = size
        return self

    def execute(self) -> _SupabaseHTTPResponse:
        if self._mode == "upsert":
            if self._upsert_json is None:
                raise _PostgrestHTTPError("upsert payload is not set")
            data = self._client.request_json(
                method="POST",
                table_name=self._table_name,
                query_params=(("on_conflict", self._on_conflict),),
                body=[dict(self._upsert_json)],
                extra_headers={
                    "Prefer": "resolution=merge-duplicates, return=representation"
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

    def __init__(self, supabase_url: str, service_role_key: str) -> None:
        self._rest_base_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._service_role_key = service_role_key

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
        url = _build_postgrest_url(self._rest_base_url, table_name, query_params)
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

        request = urllib_request.Request(
            url=url,
            data=request_body,
            headers=headers,
            method=method,
        )

        try:
            with cast(
                _ResponseReadBytesLike, urllib_request.urlopen(request)
            ) as response:
                return _parse_postgrest_json(response.read())
        except urllib_error.HTTPError as exc:
            code = _extract_postgrest_error_code(exc)
            raise _PostgrestHTTPError("postgrest request failed", code=code) from exc
        except urllib_error.URLError as exc:
            raise _PostgrestHTTPError("postgrest request failed") from exc


class _ResponseReadBytesLike(Protocol):
    def __enter__(self) -> "_ResponseReadBytesLike": ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool | None: ...

    def read(self) -> bytes: ...


def _build_postgrest_url(
    rest_base_url: str,
    table_name: str,
    query_params: tuple[tuple[str, str], ...],
) -> str:
    encoded_table = urllib_parse.quote(table_name, safe="")
    base = f"{rest_base_url}/{encoded_table}"
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


def _extract_postgrest_error_code(exc: urllib_error.HTTPError) -> str | None:
    try:
        payload = _parse_postgrest_json(exc.read())
    except Exception:
        return None
    if not isinstance(payload, Mapping):
        return None
    payload_map = cast(Mapping[str, object], payload)
    code = payload_map.get("code")
    if isinstance(code, str) and code.strip():
        return code.strip()
    return None


def _to_postgrest_eq_filter(value: object) -> str:
    if isinstance(value, bool):
        encoded = "true" if value else "false"
    else:
        encoded = str(value)
    return f"eq.{encoded}"


class SupabaseWriterError(RuntimeError):
    category: str
    code: str
    context: dict[str, object]

    def __init__(
        self,
        message: str,
        *,
        category: str,
        code: str,
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.code = code
        self.context = dict(context or {})


class SupabaseConfigError(SupabaseWriterError):
    def __init__(
        self, message: str, *, code: str, context: dict[str, object] | None = None
    ) -> None:
        super().__init__(
            message,
            category="config",
            code=code,
            context=context,
        )


class SupabaseArgumentError(SupabaseWriterError):
    def __init__(
        self, message: str, *, code: str, context: dict[str, object] | None = None
    ) -> None:
        super().__init__(
            message,
            category="argument",
            code=code,
            context=context,
        )


class SupabaseRemoteError(SupabaseWriterError):
    def __init__(
        self, message: str, *, code: str, context: dict[str, object] | None = None
    ) -> None:
        super().__init__(
            message,
            category="remote",
            code=code,
            context=context,
        )


class SupabaseWriter:
    def __init__(self, *, client: SupabaseClientLike | None, dry_run: bool) -> None:
        self._client: SupabaseClientLike | None = client
        self.dry_run: bool = dry_run

        if not self.dry_run and self._client is None:
            raise SupabaseConfigError(
                "supabase client is not initialized",
                code="missing_client",
            )

    @classmethod
    def from_env(
        cls,
        dry_run: bool,
        *,
        client_factory: ClientFactory | None = None,
    ) -> "SupabaseWriter":
        if dry_run:
            return cls(client=None, dry_run=True)

        supabase_url = _require_env("SUPABASE_URL")
        service_role_key = _require_env("SUPABASE_SERVICE_ROLE_KEY")

        factory = client_factory or _default_client_factory
        try:
            client = factory(supabase_url, service_role_key)
        except SupabaseWriterError:
            raise
        except Exception as exc:
            raise SupabaseConfigError(
                "failed to initialize supabase client",
                code="client_init_failed",
            ) from exc

        return cls(client=client, dry_run=False)

    def upsert_upload_index(
        self,
        payload: dict[str, object],
        *,
        progress_callback: Callable[[], None] | None = None,
    ) -> None:
        run_dir = _required_str(payload, "run_dir")
        run_json = _required_json_object(payload, "run_json")
        images = _optional_object_list(payload.get("images"), field="images")

        def _tick_progress() -> None:
            if progress_callback is not None:
                progress_callback()

        if self.dry_run:
            return

        run_id = self._upsert_run(run_dir, run_json)
        _tick_progress()
        for image in images:
            image_id = self._upsert_image(run_id, image, run_dir=run_dir)
            _tick_progress()
            variants = _optional_object_list(
                image.get("variants"), field="images[].variants"
            )
            for variant in variants:
                self._upsert_image_variant(image_id, variant, run_dir=run_dir)
                _tick_progress()

    def _upsert_run(self, run_dir: str, run_json: Mapping[str, object]) -> str:
        safe_context = {
            "run_dir_hash12": _hash12(run_dir),
            "run_dir_len": len(run_dir),
        }
        row = {
            "run_dir": run_dir,
            "run_json": dict(run_json),
        }
        data = self._execute_upsert(
            table_name="runs",
            row=row,
            on_conflict="run_dir",
            context=safe_context,
        )
        run_id = _extract_id_from_data(data)
        if run_id is not None:
            return run_id

        return self._lookup_id(
            table_name="runs",
            filters=(("run_dir", run_dir),),
            context=safe_context,
        )

    def _upsert_image(
        self,
        run_id: str,
        image: Mapping[str, object],
        *,
        run_dir: str,
    ) -> str:
        x_index = _required_int(image, "x_index")
        y_index = _required_int(image, "y_index")
        batch_index = _int_with_default(image, "batch_index", default=0)
        category = _required_str(image, "category")
        metadata = _required_json_object(image, "metadata")

        safe_context = {
            "run_dir_hash12": _hash12(run_dir),
            "x_index": x_index,
            "y_index": y_index,
            "batch_index": batch_index,
        }
        row: dict[str, object] = {
            "run_id": run_id,
            "x_index": x_index,
            "y_index": y_index,
            "batch_index": batch_index,
            "category": category,
            "metadata": dict(metadata),
        }

        width = _optional_int(image.get("width"), field="width")
        height = _optional_int(image.get("height"), field="height")
        blurhash = _optional_str(image.get("blurhash"), field="blurhash")
        if width is not None:
            row["width"] = width
        if height is not None:
            row["height"] = height
        if blurhash is not None:
            row["blurhash"] = blurhash

        data = self._execute_upsert(
            table_name="images",
            row=row,
            on_conflict="run_id,x_index,y_index,batch_index",
            context=safe_context,
        )
        image_id = _extract_id_from_data(data)
        if image_id is not None:
            return image_id

        return self._lookup_id(
            table_name="images",
            filters=(
                ("run_id", run_id),
                ("x_index", x_index),
                ("y_index", y_index),
                ("batch_index", batch_index),
            ),
            context=safe_context,
        )

    def _upsert_image_variant(
        self,
        image_id: str,
        variant: Mapping[str, object],
        *,
        run_dir: str,
    ) -> None:
        variant_name = _required_str(variant, "variant")
        bucket = _required_str(variant, "bucket")
        r2_key = _required_str(variant, "r2_key")
        content_type = _required_str(variant, "content_type")

        safe_context = {
            "run_dir_hash12": _hash12(run_dir),
            "variant": variant_name,
            "bucket": bucket,
            "r2_key_hash12": _hash12(r2_key),
            "r2_key_len": len(r2_key),
        }
        row: dict[str, object] = {
            "image_id": image_id,
            "variant": variant_name,
            "bucket": bucket,
            "r2_key": r2_key,
            "content_type": content_type,
        }

        byte_size = _optional_int(variant.get("byte_size"), field="byte_size")
        width = _optional_int(variant.get("width"), field="width")
        height = _optional_int(variant.get("height"), field="height")
        webp_quality = _optional_int(variant.get("webp_quality"), field="webp_quality")
        avif_quality = _optional_int(variant.get("avif_quality"), field="avif_quality")
        avif_speed = _optional_int(variant.get("avif_speed"), field="avif_speed")
        sha256 = _optional_str(variant.get("sha256"), field="sha256")

        if byte_size is not None:
            row["byte_size"] = byte_size
        if width is not None:
            row["width"] = width
        if height is not None:
            row["height"] = height
        if webp_quality is not None:
            row["webp_quality"] = webp_quality
        if avif_quality is not None:
            row["avif_quality"] = avif_quality
        if avif_speed is not None:
            row["avif_speed"] = avif_speed
        if sha256 is not None:
            row["sha256"] = sha256

        _ = self._execute_upsert(
            table_name="image_variants",
            row=row,
            on_conflict="image_id,variant",
            context=safe_context,
        )

    def _execute_upsert(
        self,
        *,
        table_name: str,
        row: Mapping[str, object],
        on_conflict: str,
        context: Mapping[str, object],
    ) -> object:
        query = (
            self._require_client()
            .table(table_name)
            .upsert(
                row,
                on_conflict=on_conflict,
            )
        )
        return self._execute_query(
            query,
            table_name=table_name,
            operation="upsert",
            context=context,
        )

    def _lookup_id(
        self,
        *,
        table_name: str,
        filters: tuple[tuple[str, object], ...],
        context: Mapping[str, object],
    ) -> str:
        query = self._require_client().table(table_name).select("id")
        for key, value in filters:
            query = query.eq(key, value)
        query = query.limit(1)
        data = self._execute_query(
            query,
            table_name=table_name,
            operation="select_id",
            context=context,
        )
        row_id = _extract_id_from_data(data)
        if row_id is None:
            raise SupabaseRemoteError(
                "failed to resolve id after upsert",
                code="id_lookup_failed",
                context={"table": table_name, **context},
            )
        return row_id

    def _execute_query(
        self,
        query: SupabaseQueryLike,
        *,
        table_name: str,
        operation: str,
        context: Mapping[str, object],
    ) -> object:
        try:
            response = query.execute()
        except Exception as exc:
            remote_code = _extract_remote_code(exc)
            error_context = {
                "table": table_name,
                "operation": operation,
                **context,
            }
            if remote_code is not None:
                error_context["remote_code"] = remote_code
            raise SupabaseRemoteError(
                "supabase request failed",
                code="request_failed",
                context=error_context,
            ) from exc
        return getattr(response, "data", None)

    def _require_client(self) -> SupabaseClientLike:
        if self._client is None:
            raise SupabaseConfigError(
                "supabase client is not initialized",
                code="missing_client",
            )
        return self._client


def upsert_upload_index(
    payload: dict[str, object],
    *,
    progress_callback: Callable[[], None] | None = None,
) -> None:
    SupabaseWriter.from_env(dry_run=False).upsert_upload_index(
        payload, progress_callback=progress_callback
    )


def _default_client_factory(
    supabase_url: str, service_role_key: str
) -> SupabaseClientLike:
    try:
        client = _PostgrestHTTPClient(supabase_url, service_role_key)
        return cast(SupabaseClientLike, cast(object, client))
    except Exception as exc:
        raise SupabaseConfigError(
            "failed to initialize supabase client",
            code="client_init_failed",
        ) from exc


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise SupabaseConfigError(
            _MISSING_ENV_MESSAGE,
            code="missing_env",
            context={"missing_env": name},
        )
    return value.strip()


def _required_str(data: Mapping[str, object], field: str) -> str:
    raw = data.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise SupabaseArgumentError(
            "payload field must be a non-empty string",
            code="invalid_payload",
            context={"field": field, "expected": "str"},
        )
    return raw.strip()


def _required_int(data: Mapping[str, object], field: str) -> int:
    raw = data.get(field)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise SupabaseArgumentError(
            "payload field must be an integer",
            code="invalid_payload",
            context={"field": field, "expected": "int"},
        )
    return raw


def _int_with_default(data: Mapping[str, object], field: str, *, default: int) -> int:
    raw = data.get(field)
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise SupabaseArgumentError(
            "payload field must be an integer",
            code="invalid_payload",
            context={"field": field, "expected": "int"},
        )
    return raw


def _required_json_object(
    data: Mapping[str, object], field: str
) -> Mapping[str, object]:
    raw = data.get(field)
    if not isinstance(raw, Mapping):
        raise SupabaseArgumentError(
            "payload field must be a JSON object",
            code="invalid_payload",
            context={"field": field, "expected": "object"},
        )
    return cast(Mapping[str, object], raw)


def _optional_object_list(value: object, *, field: str) -> list[Mapping[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SupabaseArgumentError(
            "payload field must be an array",
            code="invalid_payload",
            context={"field": field, "expected": "array"},
        )

    result: list[Mapping[str, object]] = []
    items = cast(list[object], value)
    for item in items:
        if not isinstance(item, Mapping):
            raise SupabaseArgumentError(
                "array item must be an object",
                code="invalid_payload",
                context={"field": field, "expected": "object[]"},
            )
        result.append(cast(Mapping[str, object], item))
    return result


def _optional_int(value: object, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SupabaseArgumentError(
            "payload field must be an integer",
            code="invalid_payload",
            context={"field": field, "expected": "int|null"},
        )
    return value


def _optional_str(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SupabaseArgumentError(
            "payload field must be a string",
            code="invalid_payload",
            context={"field": field, "expected": "str|null"},
        )
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed


def _extract_id_from_data(data: object) -> str | None:
    if not isinstance(data, list) or not data:
        return None

    rows = cast(list[object], data)
    first_obj = rows[0]
    if not isinstance(first_obj, Mapping):
        return None

    first = cast(Mapping[str, object], first_obj)
    value = first.get("id")
    if not isinstance(value, str) or not value:
        return None
    return value


def _extract_remote_code(exc: Exception) -> str | None:
    raw_code = getattr(exc, "code", None)
    if isinstance(raw_code, str) and raw_code.strip():
        return raw_code.strip()
    return None


def _hash12(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
