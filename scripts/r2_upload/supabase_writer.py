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

    def __init__(
        self,
        *,
        client: SupabaseClientLike | None,
        dry_run: bool,
        upsert_batch_size: int = 100,
        upsert_max_bytes: int = 4_000_000,
    ) -> None:
        self._client: SupabaseClientLike | None = client
        self.dry_run: bool = dry_run
        self._upsert_batch_size = upsert_batch_size
        self._upsert_max_bytes = upsert_max_bytes

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
        return cls(
            client=client,
            dry_run=False,
            upsert_batch_size=upsert_batch_size,
            upsert_max_bytes=upsert_max_bytes,
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
            run_assets = optional_object_list(
                payload.get("run_assets"), field="run_assets"
            )
        except PayloadValidationError as exc:
            raise _to_argument_error(exc) from exc

        def _tick_progress() -> None:
            if progress_callback is not None:
                progress_callback()

        def _tick_progress_many(count: int) -> None:
            for _ in range(count):
                _tick_progress()

        if self.dry_run:
            return
        try:
            run_row = self._build_run_row(payload, run_dir=run_dir, run_json=run_json)
        except PayloadValidationError as exc:
            raise _to_argument_error(exc) from exc
        run_id, created_at = self._upsert_run(run_row, run_dir=run_dir)
        _tick_progress()

        try:
            run_snapshot_row = self._build_run_snapshot_row(
                run_id,
                run_dir=run_dir,
                run_json=run_json,
            )
        except PayloadValidationError as exc:
            raise _to_argument_error(exc) from exc
        self._upsert_run_snapshot(run_snapshot_row)
        _tick_progress()

        try:
            run_list_item_row = self._build_run_list_item_row(
                payload,
                run_id=run_id,
                run_dir=run_dir,
                created_at=created_at,
                run_assets=run_assets,
            )
        except PayloadValidationError as exc:
            raise _to_argument_error(exc) from exc
        self._upsert_run_list_item(run_list_item_row)
        _tick_progress()

        grid_item_rows: list[dict[str, object]] = []
        grid_item_snapshot_rows: list[dict[str, object]] = []
        for image in images:
            try:
                row, snapshot_row = self._build_grid_item_row(
                    run_id,
                    image,
                    run_dir=run_dir,
                )
            except PayloadValidationError as exc:
                raise _to_argument_error(exc) from exc
            grid_item_rows.append(row)
            grid_item_snapshot_rows.append(snapshot_row)

        self._upsert_run_grid_items_batch(grid_item_rows)
        _tick_progress_many(len(grid_item_rows))

        self._upsert_run_grid_item_snapshots_batch(grid_item_snapshot_rows)
        _tick_progress_many(len(grid_item_snapshot_rows))

        grid_cell_rows = self._build_run_grid_cells_rows(
            run_id=run_id,
            run_dir=run_dir,
            grid_item_rows=grid_item_rows,
        )
        self._upsert_run_grid_cells_batch(grid_cell_rows)
        _tick_progress_many(len(grid_cell_rows))

    def _build_run_row(
        self,
        payload: Mapping[str, object],
        *,
        run_dir: str,
        run_json: Mapping[str, object],
    ) -> dict[str, object]:
        x_columns = _required_object_list_field(payload, "x_columns")
        y_indexes = _required_int_list_field(payload, "y_indexes")
        x_count = required_int(payload, "x_count")
        y_count = required_int(payload, "y_count")
        total_cells = required_int(payload, "total_cells")

        row: dict[str, object] = {
            "run_dir": run_dir,
            "run_id": required_str(payload, "run_id"),
            "x_columns": x_columns,
            "y_indexes": y_indexes,
            "x_count": x_count,
            "y_count": y_count,
            "total_cells": total_cells,
            "model_name": optional_str(payload.get("model_name"), field="model_name"),
            "model_description_zh": optional_str(
                payload.get("model_description_zh"), field="model_description_zh"
            ),
            "model_description_en": optional_str(
                payload.get("model_description_en"), field="model_description_en"
            ),
            "model_homepage": optional_str(
                payload.get("model_homepage"), field="model_homepage"
            ),
            "model_huggingface": optional_str(
                payload.get("model_huggingface"), field="model_huggingface"
            ),
            "model_civitai": optional_str(
                payload.get("model_civitai"), field="model_civitai"
            ),
            "workflow_download_r2_key": optional_str(
                payload.get("workflow_download_r2_key"),
                field="workflow_download_r2_key",
            ),
            "workflow_download_sha256": optional_str(
                payload.get("workflow_download_sha256"),
                field="workflow_download_sha256",
            ),
        }
        created_at = _optional_required_string(run_json.get("created_at"))
        if created_at is not None:
            row["created_at"] = created_at
        return row

    def _upsert_run(
        self, row: Mapping[str, object], *, run_dir: str
    ) -> tuple[str, str]:
        safe_context = {
            "run_dir_hash12": hash12(run_dir),
            "run_dir_len": len(run_dir),
        }
        data = self._execute_upsert(
            table_name="runs",
            row_or_rows=dict(row),
            on_conflict="run_dir",
            select_columns="id,created_at",
            returning_mode="representation",
            context=safe_context,
        )
        rows = extract_rows_from_data(data)
        if rows:
            first_row = rows[0]
            run_id = first_row.get("id")
            created_at = first_row.get("created_at")
            if isinstance(run_id, str) and run_id:
                if isinstance(created_at, str) and created_at.strip():
                    return run_id, created_at
                return run_id, self._lookup_string_field(
                    table_name="runs",
                    field_name="created_at",
                    filters=(("run_dir", run_dir),),
                    context=safe_context,
                )
        run_id = self._lookup_id(
            table_name="runs",
            filters=(("run_dir", run_dir),),
            context=safe_context,
        )
        return run_id, self._lookup_string_field(
            table_name="runs",
            field_name="created_at",
            filters=(("run_dir", run_dir),),
            context=safe_context,
        )

    def _build_run_snapshot_row(
        self,
        run_id: str,
        *,
        run_dir: str,
        run_json: Mapping[str, object],
    ) -> dict[str, object]:
        return {
            "run_id": run_id,
            "run_dir": run_dir,
            "run_json": dict(run_json),
        }

    def _build_run_list_item_row(
        self,
        payload: Mapping[str, object],
        *,
        run_id: str,
        run_dir: str,
        created_at: str,
        run_assets: list[Mapping[str, object]],
    ) -> dict[str, object]:
        x_count = required_int(payload, "x_count")
        y_count = required_int(payload, "y_count")
        total_cells = required_int(payload, "total_cells")

        cover: dict[str, object] | None = None
        homepage_cards_with_index: list[tuple[int, dict[str, object]]] = []
        for run_asset in run_assets:
            asset_role = required_str(run_asset, "asset_role")
            asset_index = int_with_default(run_asset, "asset_index", default=0)
            summary = self._build_run_asset_summary(run_asset)
            if asset_role == "cover":
                if cover is None:
                    cover = summary
                continue
            if asset_role == "homepage_card":
                homepage_cards_with_index.append((asset_index, summary))

        homepage_cards_with_index.sort(key=lambda item: item[0])

        row: dict[str, object] = {
            "run_id": run_id,
            "run_dir": run_dir,
            "created_at": created_at,
            "x_count": x_count,
            "y_count": y_count,
            "total_cells": total_cells,
            "model_name": optional_str(payload.get("model_name"), field="model_name"),
            "model_description_zh": optional_str(
                payload.get("model_description_zh"),
                field="model_description_zh",
            ),
            "model_description_en": optional_str(
                payload.get("model_description_en"),
                field="model_description_en",
            ),
            "model_homepage": optional_str(
                payload.get("model_homepage"),
                field="model_homepage",
            ),
            "model_huggingface": optional_str(
                payload.get("model_huggingface"),
                field="model_huggingface",
            ),
            "model_civitai": optional_str(
                payload.get("model_civitai"),
                field="model_civitai",
            ),
            "cover": cover,
            "homepage_cards": [summary for _, summary in homepage_cards_with_index],
        }
        return row

    def _build_run_asset_summary(
        self,
        run_asset: Mapping[str, object],
    ) -> dict[str, object]:
        variants = optional_object_list(
            run_asset.get("variants"), field="run_assets[].variants"
        )
        variant_lookup = self._variant_lookup(variants)
        return {
            "width": optional_int(run_asset.get("width"), field="width"),
            "height": optional_int(run_asset.get("height"), field="height"),
            "blurhash": optional_str(run_asset.get("blurhash"), field="blurhash"),
            "blurhash_width": optional_int(
                run_asset.get("blurhash_width"), field="blurhash_width"
            ),
            "blurhash_height": optional_int(
                run_asset.get("blurhash_height"), field="blurhash_height"
            ),
            "thumb_webp_r2_key": self._variant_r2_key(variant_lookup, "thumb_webp"),
            "thumb_avif_r2_key": self._variant_r2_key(variant_lookup, "thumb_avif"),
            "display_webp_r2_key": self._variant_r2_key(variant_lookup, "display_webp"),
            "display_avif_r2_key": self._variant_r2_key(variant_lookup, "display_avif"),
        }

    def _build_grid_item_row(
        self,
        run_id: str,
        image: Mapping[str, object],
        *,
        run_dir: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        x_index = required_int(image, "x_index")
        y_index = required_int(image, "y_index")
        batch_index = int_with_default(image, "batch_index", default=0)
        category = required_str(image, "category")
        metadata = required_json_object(image, "metadata")
        variants = optional_object_list(
            image.get("variants"), field="images[].variants"
        )
        variant_lookup = self._variant_lookup(variants)

        row: dict[str, object] = {
            "run_id": run_id,
            "run_dir": run_dir,
            "x_index": x_index,
            "y_index": y_index,
            "batch_index": batch_index,
            "category": category,
            "width": optional_int(image.get("width"), field="width"),
            "height": optional_int(image.get("height"), field="height"),
            "blurhash": optional_str(image.get("blurhash"), field="blurhash"),
            "seed": self._read_seed_string(image, metadata),
            "prompt_hash": _optional_required_string(image.get("prompt_hash"))
            or _optional_required_string(metadata.get("prompt_hash")),
            "positive_prompt": _optional_required_string(image.get("positive_prompt"))
            or _optional_required_string(metadata.get("positive_prompt")),
            "y_value": _optional_required_string(image.get("y_value"))
            or _optional_required_string(metadata.get("y_value")),
            "thumb_webp_bucket": self._variant_bucket(variant_lookup, "thumb_webp"),
            "thumb_webp_r2_key": self._variant_r2_key(variant_lookup, "thumb_webp"),
            "thumb_avif_bucket": self._variant_bucket(variant_lookup, "thumb_avif"),
            "thumb_avif_r2_key": self._variant_r2_key(variant_lookup, "thumb_avif"),
            "display_webp_bucket": self._variant_bucket(variant_lookup, "display_webp"),
            "display_webp_r2_key": self._variant_r2_key(variant_lookup, "display_webp"),
            "display_avif_bucket": self._variant_bucket(variant_lookup, "display_avif"),
            "display_avif_r2_key": self._variant_r2_key(variant_lookup, "display_avif"),
        }
        snapshot_row: dict[str, object] = {
            "run_id": run_id,
            "run_dir": run_dir,
            "x_index": x_index,
            "y_index": y_index,
            "batch_index": batch_index,
            "metadata": dict(metadata),
        }
        return row, snapshot_row

    def _build_run_grid_cells_rows(
        self,
        *,
        run_id: str,
        run_dir: str,
        grid_item_rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        representatives: dict[tuple[int, int], dict[str, object]] = {}
        for row in grid_item_rows:
            x_index = row.get("x_index")
            y_index = row.get("y_index")
            batch_index = row.get("batch_index")
            if not isinstance(x_index, int) or not isinstance(y_index, int):
                continue
            if not isinstance(batch_index, int):
                continue
            key = (x_index, y_index)
            existing = representatives.get(key)
            representative_batch_index = (
                existing.get("representative_batch_index")
                if existing is not None
                else None
            )
            if existing is None or (
                not isinstance(representative_batch_index, int)
                or batch_index < representative_batch_index
            ):
                representatives[key] = {
                    "run_id": run_id,
                    "run_dir": run_dir,
                    "x_index": x_index,
                    "y_index": y_index,
                    "representative_batch_index": batch_index,
                    "category": row.get("category"),
                    "width": row.get("width"),
                    "height": row.get("height"),
                    "blurhash": row.get("blurhash"),
                }
        return list(representatives.values())

    def _upsert_run_snapshot(self, row: Mapping[str, object]) -> None:
        _ = self._execute_upsert(
            table_name="run_snapshots",
            row_or_rows=dict(row),
            on_conflict="run_id",
            select_columns=None,
            returning_mode="minimal",
            context={"run_dir": row.get("run_dir")},
        )

    def _upsert_run_list_item(self, row: Mapping[str, object]) -> None:
        _ = self._execute_upsert(
            table_name="run_list_items",
            row_or_rows=dict(row),
            on_conflict="run_id",
            select_columns=None,
            returning_mode="minimal",
            context={"run_dir": row.get("run_dir")},
        )

    def _upsert_run_grid_items_batch(self, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        for chunk in self._iter_row_chunks(rows):
            normalized_chunk = _normalize_rows_for_postgrest(chunk)
            _ = self._execute_upsert(
                table_name="run_grid_items",
                row_or_rows=normalized_chunk,
                on_conflict="run_id,x_index,y_index,batch_index",
                select_columns=None,
                returning_mode="minimal",
                context={"chunk_size": len(normalized_chunk)},
            )

    def _upsert_run_grid_item_snapshots_batch(
        self, rows: list[dict[str, object]]
    ) -> None:
        if not rows:
            return
        for chunk in self._iter_row_chunks(rows):
            normalized_chunk = _normalize_rows_for_postgrest(chunk)
            _ = self._execute_upsert(
                table_name="run_grid_item_snapshots",
                row_or_rows=normalized_chunk,
                on_conflict="run_id,x_index,y_index,batch_index",
                select_columns=None,
                returning_mode="minimal",
                context={"chunk_size": len(normalized_chunk)},
            )

    def _upsert_run_grid_cells_batch(self, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        for chunk in self._iter_row_chunks(rows):
            normalized_chunk = _normalize_rows_for_postgrest(chunk)
            _ = self._execute_upsert(
                table_name="run_grid_cells",
                row_or_rows=normalized_chunk,
                on_conflict="run_id,x_index,y_index",
                select_columns=None,
                returning_mode="minimal",
                context={"chunk_size": len(normalized_chunk)},
            )

    def _variant_lookup(
        self, variants: list[Mapping[str, object]]
    ) -> dict[str, Mapping[str, object]]:
        lookup: dict[str, Mapping[str, object]] = {}
        for variant in variants:
            variant_name = required_str(variant, "variant")
            lookup[variant_name] = variant
        return lookup

    def _variant_bucket(
        self, lookup: Mapping[str, Mapping[str, object]], variant_name: str
    ) -> str | None:
        variant = lookup.get(variant_name)
        if variant is None:
            return None
        return optional_str(variant.get("bucket"), field=f"{variant_name}.bucket")

    def _variant_r2_key(
        self, lookup: Mapping[str, Mapping[str, object]], variant_name: str
    ) -> str | None:
        variant = lookup.get(variant_name)
        if variant is None:
            return None
        return optional_str(variant.get("r2_key"), field=f"{variant_name}.r2_key")

    def _read_seed_string(
        self,
        image: Mapping[str, object],
        metadata: Mapping[str, object],
    ) -> str | None:
        seed = _optional_int_field(image, "seed")
        if seed is None:
            seed = optional_int(metadata.get("seed"), field="metadata.seed")
        if seed is None:
            return None
        return str(seed)

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

    def _lookup_string_field(
        self,
        *,
        table_name: str,
        field_name: str,
        filters: tuple[tuple[str, object], ...],
        context: Mapping[str, object],
    ) -> str:
        query = self._require_client().table(table_name).select(field_name)
        for key, value in filters:
            query = query.eq(key, value)
        query = query.limit(1)
        data = self._execute_query(
            query,
            table_name=table_name,
            operation=f"select_{field_name}",
            context=context,
        )
        rows = extract_rows_from_data(data)
        if rows:
            value = rows[0].get(field_name)
            if isinstance(value, str) and value.strip():
                return value
        raise SupabaseRemoteError(
            "failed to resolve field after upsert",
            code="field_lookup_failed",
            context={"table": table_name, "field": field_name, **context},
        )

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


def estimate_upload_index_records(payload: Mapping[str, object]) -> int:
    images = optional_object_list(payload.get("images"), field="images")
    unique_grid_cells: set[tuple[int, int]] = set()
    for image in images:
        x_index = int_with_default(image, "x_index", default=0)
        y_index = int_with_default(image, "y_index", default=0)
        unique_grid_cells.add((x_index, y_index))
    return 3 + len(images) + len(images) + len(unique_grid_cells)


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


def _optional_required_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _optional_int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in cast(list[object], value):
        if isinstance(item, int) and not isinstance(item, bool):
            result.append(item)
    return result


def _required_int_list_field(obj: Mapping[str, object], key: str) -> list[int]:
    if key not in obj:
        raise PayloadValidationError(
            "payload field must be an integer array",
            field=key,
            expected="int[]",
        )
    return _optional_int_list(obj.get(key))


def _optional_int_field(obj: Mapping[str, object], key: str) -> int | None:
    return optional_int(obj.get(key), field=key)


def _required_object_list_field(
    obj: Mapping[str, object], key: str
) -> list[Mapping[str, object]]:
    if key not in obj:
        raise PayloadValidationError(
            "payload field must be an array",
            field=key,
            expected="object[]",
        )
    return optional_object_list(obj.get(key), field=key)
