from __future__ import annotations

# pyright: reportPrivateUsage=false,reportUnusedImport=false
import json
from collections.abc import Callable, Mapping
from typing import Protocol, cast

from .postgrest_http import (
    _build_postgrest_path,
    _extract_postgrest_error_code_from_raw,
    _parse_postgrest_json,
    _PostgrestHTTPClient,
    _PostgrestHTTPError,
    _PostgrestHTTPQuery,
    _retry_backoff_seconds,
    _SupabaseHTTPResponse,
    _to_postgrest_eq_filter,
)
from .supabase_env import (
    InvalidEnvIntError,
    MissingRequiredEnvError,
    optional_env_int,
    require_env,
)
from .supabase_normalize import (
    PayloadValidationError,
    extract_id_from_data,
    extract_remote_code,
    extract_rows_from_data,
    hash12,
    int_with_default,
    normalize_rows_for_postgrest as _normalize_rows_for_postgrest,
    optional_int,
    optional_object_list,
    optional_str,
    required_int,
    required_json_object,
    required_str,
)

_MISSING_ENV_MESSAGE = "missing required Supabase configuration"


class SupabaseResponseLike(Protocol):
    data: object


class SupabaseQueryLike(Protocol):
    def upsert(self, json: object, *, on_conflict: str) -> "SupabaseQueryLike": ...
    def select(self, columns: str) -> "SupabaseQueryLike": ...
    def returning(self, mode: str) -> "SupabaseQueryLike": ...
    def eq(self, column: str, value: object) -> "SupabaseQueryLike": ...
    def limit(self, size: int) -> "SupabaseQueryLike": ...
    def execute(self) -> SupabaseResponseLike: ...


class SupabaseClientLike(Protocol):
    def table(self, table_name: str) -> SupabaseQueryLike: ...


ClientFactory = Callable[[str, str], SupabaseClientLike]


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
    _upsert_batch_size: int
    _upsert_max_bytes: int
    _db_concurrency: int

    def __init__(
        self,
        *,
        client: SupabaseClientLike | None,
        dry_run: bool,
        upsert_batch_size: int = 100,
        upsert_max_bytes: int = 4_000_000,
        db_concurrency: int = 1,
    ) -> None:
        self._client: SupabaseClientLike | None = client
        self.dry_run: bool = dry_run
        self._upsert_batch_size = upsert_batch_size
        self._upsert_max_bytes = upsert_max_bytes
        self._db_concurrency = db_concurrency

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
        supabase_url = _require_env_value("SUPABASE_URL")
        service_role_key = _require_env_value("SUPABASE_SERVICE_ROLE_KEY")
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
        upsert_batch_size = _optional_env_int_value(
            "SUPABASE_UPSERT_BATCH_SIZE", default=100
        )
        if upsert_batch_size < 1:
            raise SupabaseConfigError(
                "invalid supabase batch configuration",
                code="invalid_batch_size",
            )
        upsert_max_bytes = _optional_env_int_value(
            "SUPABASE_UPSERT_MAX_BYTES", default=4_000_000
        )
        if upsert_max_bytes < 1024:
            raise SupabaseConfigError(
                "invalid supabase batch configuration",
                code="invalid_batch_max_bytes",
            )
        db_concurrency = _optional_env_int_value("SUPABASE_DB_CONCURRENCY", default=1)
        if db_concurrency < 1:
            raise SupabaseConfigError(
                "invalid supabase db concurrency",
                code="invalid_db_concurrency",
            )
        return cls(
            client=client,
            dry_run=False,
            upsert_batch_size=upsert_batch_size,
            upsert_max_bytes=upsert_max_bytes,
            db_concurrency=db_concurrency,
        )

    def upsert_upload_index(
        self,
        payload: dict[str, object],
        *,
        progress_callback: Callable[[], None] | None = None,
    ) -> None:
        try:
            run_dir = required_str(payload, "run_dir")
            run_json = required_json_object(payload, "run_json")
            images = optional_object_list(payload.get("images"), field="images")
        except PayloadValidationError as exc:
            raise _to_argument_error(exc) from exc

        def _tick_progress() -> None:
            if progress_callback is not None:
                progress_callback()

        if self.dry_run:
            return
        run_id = self._upsert_run(run_dir, run_json)
        _tick_progress()
        image_rows: list[dict[str, object]] = []
        image_contexts: list[dict[str, object]] = []
        image_variant_lists: list[list[Mapping[str, object]]] = []
        image_lookup_keys: list[tuple[object, object, object, object]] = []
        for image in images:
            row, context, lookup_key, variants = self._build_image_row(
                run_id,
                image,
                run_dir=run_dir,
            )
            image_rows.append(row)
            image_contexts.append(context)
            image_variant_lists.append(variants)
            image_lookup_keys.append(lookup_key)
        image_ids_by_key = self._upsert_images_batch(image_rows)
        variant_rows: list[dict[str, object]] = []
        for index, variants in enumerate(image_variant_lists):
            lookup_key = image_lookup_keys[index]
            image_id = image_ids_by_key.get(lookup_key)
            if image_id is None:
                image_id = self._lookup_id(
                    table_name="images",
                    filters=(
                        ("run_id", run_id),
                        ("x_index", lookup_key[1]),
                        ("y_index", lookup_key[2]),
                        ("batch_index", lookup_key[3]),
                    ),
                    context=image_contexts[index],
                )
            _tick_progress()
            for variant in variants:
                row = self._build_variant_row(image_id, variant, run_dir=run_dir)
                variant_rows.append(row)
                _tick_progress()
        self._upsert_variants_batch(variant_rows)

    def _upsert_run(self, run_dir: str, run_json: Mapping[str, object]) -> str:
        safe_context = {
            "run_dir_hash12": hash12(run_dir),
            "run_dir_len": len(run_dir),
        }
        row = {
            "run_dir": run_dir,
            "run_json": dict(run_json),
        }
        data = self._execute_upsert(
            table_name="runs",
            row_or_rows=row,
            on_conflict="run_dir",
            select_columns="id",
            returning_mode="representation",
            context=safe_context,
        )
        run_id = extract_id_from_data(data)
        if run_id is not None:
            return run_id
        return self._lookup_id(
            table_name="runs",
            filters=(("run_dir", run_dir),),
            context=safe_context,
        )

    def _build_image_row(
        self,
        run_id: str,
        image: Mapping[str, object],
        *,
        run_dir: str,
    ) -> tuple[
        dict[str, object],
        dict[str, object],
        tuple[object, object, object, object],
        list[Mapping[str, object]],
    ]:
        x_index = required_int(image, "x_index")
        y_index = required_int(image, "y_index")
        batch_index = int_with_default(image, "batch_index", default=0)
        category = required_str(image, "category")
        metadata = required_json_object(image, "metadata")
        safe_context: dict[str, object] = {
            "run_dir_hash12": hash12(run_dir),
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
        width = optional_int(image.get("width"), field="width")
        height = optional_int(image.get("height"), field="height")
        blurhash = optional_str(image.get("blurhash"), field="blurhash")
        if width is not None:
            row["width"] = width
        if height is not None:
            row["height"] = height
        if blurhash is not None:
            row["blurhash"] = blurhash
        variants = optional_object_list(
            image.get("variants"), field="images[].variants"
        )
        return (
            row,
            safe_context,
            (run_id, x_index, y_index, batch_index),
            variants,
        )

    def _build_variant_row(
        self,
        image_id: str,
        variant: Mapping[str, object],
        *,
        run_dir: str,
    ) -> dict[str, object]:
        _ = run_dir
        variant_name = required_str(variant, "variant")
        bucket = required_str(variant, "bucket")
        r2_key = required_str(variant, "r2_key")
        content_type = required_str(variant, "content_type")
        row: dict[str, object] = {
            "image_id": image_id,
            "variant": variant_name,
            "bucket": bucket,
            "r2_key": r2_key,
            "content_type": content_type,
        }
        byte_size = optional_int(variant.get("byte_size"), field="byte_size")
        width = optional_int(variant.get("width"), field="width")
        height = optional_int(variant.get("height"), field="height")
        webp_quality = optional_int(variant.get("webp_quality"), field="webp_quality")
        avif_quality = optional_int(variant.get("avif_quality"), field="avif_quality")
        avif_speed = optional_int(variant.get("avif_speed"), field="avif_speed")
        sha256 = optional_str(variant.get("sha256"), field="sha256")
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
        return row

    def _upsert_images_batch(
        self,
        rows: list[dict[str, object]],
    ) -> dict[tuple[object, object, object, object], str]:
        if not rows:
            return {}
        mapped: dict[tuple[object, object, object, object], str] = {}
        for chunk in self._iter_row_chunks(rows):
            normalized_chunk = _normalize_rows_for_postgrest(chunk)
            data = self._execute_upsert(
                table_name="images",
                row_or_rows=normalized_chunk,
                on_conflict="run_id,x_index,y_index,batch_index",
                select_columns="id,run_id,x_index,y_index,batch_index",
                returning_mode="representation",
                context={"chunk_size": len(normalized_chunk)},
            )
            for row in extract_rows_from_data(data):
                key = (
                    row.get("run_id"),
                    row.get("x_index"),
                    row.get("y_index"),
                    row.get("batch_index"),
                )
                row_id = row.get("id")
                if isinstance(row_id, str) and row_id:
                    mapped[key] = row_id
        return mapped

    def _upsert_variants_batch(self, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        chunks = list(self._iter_row_chunks(rows))
        if self._db_concurrency <= 1 or len(chunks) <= 1:
            for chunk in chunks:
                normalized_chunk = _normalize_rows_for_postgrest(chunk)
                _ = self._execute_upsert(
                    table_name="image_variants",
                    row_or_rows=normalized_chunk,
                    on_conflict="image_id,variant",
                    select_columns=None,
                    returning_mode="minimal",
                    context={"chunk_size": len(normalized_chunk)},
                )
            return
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=self._db_concurrency) as pool:
            futures = [
                pool.submit(
                    self._execute_upsert,
                    table_name="image_variants",
                    row_or_rows=_normalize_rows_for_postgrest(chunk),
                    on_conflict="image_id,variant",
                    select_columns=None,
                    returning_mode="minimal",
                    context={"chunk_size": len(chunk)},
                )
                for chunk in chunks
            ]
            for future in as_completed(futures):
                _ = future.result()

    def _execute_upsert(
        self,
        *,
        table_name: str,
        row_or_rows: (
            Mapping[str, object] | list[Mapping[str, object]] | list[dict[str, object]]
        ),
        on_conflict: str,
        select_columns: str | None,
        returning_mode: str,
        context: Mapping[str, object],
    ) -> object:
        query = (
            self._require_client()
            .table(table_name)
            .upsert(
                row_or_rows,
                on_conflict=on_conflict,
            )
            .returning(returning_mode)
        )
        if select_columns is not None:
            query = query.select(select_columns)
        return self._execute_query(
            query,
            table_name=table_name,
            operation="upsert",
            context=context,
        )

    def _iter_row_chunks(
        self,
        rows: list[dict[str, object]],
    ) -> list[list[dict[str, object]]]:
        chunks: list[list[dict[str, object]]] = []
        current_chunk: list[dict[str, object]] = []
        current_bytes = 2
        for row in rows:
            row_bytes = len(json.dumps(row, separators=(",", ":")).encode("utf-8"))
            projected = current_bytes + row_bytes + (1 if current_chunk else 0)
            if current_chunk and (
                len(current_chunk) >= self._upsert_batch_size
                or projected > self._upsert_max_bytes
            ):
                chunks.append(current_chunk)
                current_chunk = []
                current_bytes = 2
            current_chunk.append(row)
            current_bytes += row_bytes + (1 if len(current_chunk) > 1 else 0)
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

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
        row_id = extract_id_from_data(data)
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
            remote_code = extract_remote_code(exc)
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


def _require_env_value(name: str) -> str:
    try:
        return require_env(name)
    except MissingRequiredEnvError:
        raise SupabaseConfigError(
            _MISSING_ENV_MESSAGE,
            code="missing_env",
            context={"missing_env": name},
        )


def _optional_env_int_value(name: str, *, default: int) -> int:
    try:
        return optional_env_int(name, default=default)
    except InvalidEnvIntError as exc:
        raise SupabaseConfigError(
            "invalid supabase configuration",
            code="invalid_env",
            context={"env": name},
        ) from exc


def _to_argument_error(exc: PayloadValidationError) -> SupabaseArgumentError:
    return SupabaseArgumentError(
        str(exc),
        code="invalid_payload",
        context={"field": exc.field, "expected": exc.expected},
    )
