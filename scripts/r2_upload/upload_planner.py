# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import argparse
import copy
import hashlib
import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from .encoding_params import avif_params, webp_params
from .manifest import (
    build_view_release,
    current_view_object_key,
    view_manifest_object_key,
)
from .path_safety import normalize_run_dir, resolve_metadata_image_paths
from .r2_keys import (
    bucket_for,
    cache_control_for,
    content_type_for,
    object_key,
    workflow_object_key,
)
from .upload_contracts import (
    BucketScope,
    Category,
    PlannedImageTask,
    PlannedUpload,
    RunPlan,
    _DERIVED_IMAGE_VARIANTS,
    _IMAGE_VARIANTS,
)
from .upload_discovery import _resolve_run_dir_name, _resolve_selected_run_dirs
from .upload_io import (
    _intermediate_cache_metadata_path,
    _intermediate_variant_path,
    _load_intermediate_cache_metadata,
    _load_metadata_records,
    _load_run_json,
    _sha256_file,
    _to_json_line,
    _write_intermediate_cache_metadata,
    _write_intermediate_variant,
)
from .variants import inspect_image_metadata, plan_image_variants

LOG = logging.getLogger(__name__)
_RUN_ASSET_DEFAULT_CATEGORY: Category = "normal"


@dataclass(frozen=True)
class _CachedVariantBundle:
    original_sha256: str
    metadata: dict[str, object]
    variant_lookup: dict[str, dict[str, object]]
    cached_variant_paths: dict[str, Path]


def _int_with_default(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def _non_empty_str(value: object) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed:
            return trimmed
    return None


def _json_object(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None


def _json_object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, object], item) for item in value if isinstance(item, dict)]


def _int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    return [
        item for item in value if isinstance(item, int) and not isinstance(item, bool)
    ]


def _selection_from_run_json(run_json: dict[str, object]) -> dict[str, object] | None:
    direct = _json_object(run_json.get("selection"))
    if direct is not None:
        return direct

    config_snapshot = _json_object(run_json.get("config_snapshot"))
    if config_snapshot is None:
        return None

    return _json_object(config_snapshot.get("selection"))


def _model_from_run_json(run_json: dict[str, object]) -> dict[str, object] | None:
    return _json_object(run_json.get("model"))


def _build_run_db_fields(
    run_json: dict[str, object], *, run_dir_name: str
) -> dict[str, object]:
    selection = _selection_from_run_json(run_json)
    model = _model_from_run_json(run_json)
    description = _json_object(model.get("description") if model else None)
    links = _json_object(model.get("links") if model else None)
    x_columns = _json_object_list(selection.get("x_columns") if selection else None)
    y_indexes = _int_list(selection.get("y_indexes") if selection else None)

    x_count_raw = selection.get("x_count") if selection else None
    y_count_raw = selection.get("y_count") if selection else None
    total_cells_raw = selection.get("total_cells") if selection else None

    x_count = (
        x_count_raw
        if isinstance(x_count_raw, int) and not isinstance(x_count_raw, bool)
        else len(x_columns)
    )
    y_count = (
        y_count_raw
        if isinstance(y_count_raw, int) and not isinstance(y_count_raw, bool)
        else len(y_indexes)
    )
    total_cells = (
        total_cells_raw
        if isinstance(total_cells_raw, int) and not isinstance(total_cells_raw, bool)
        else x_count * y_count
    )
    workflow_source_path, workflow_download_sha256, _ = (
        _resolve_workflow_download_source(run_json)
    )
    workflow_download_r2_key = None
    if workflow_source_path is not None and workflow_download_sha256 is not None:
        workflow_download_r2_key = workflow_object_key(
            run_dir_name, workflow_download_sha256
        )

    return {
        "run_id": _non_empty_str(run_json.get("run_id")) or run_dir_name,
        "x_columns": x_columns,
        "y_indexes": y_indexes,
        "x_count": x_count,
        "y_count": y_count,
        "total_cells": total_cells,
        "model_name": _non_empty_str(model.get("name") if model else None),
        "model_description_zh": _non_empty_str(
            description.get("zh") if description else None
        ),
        "model_description_en": _non_empty_str(
            description.get("en") if description else None
        ),
        "model_homepage": _non_empty_str(links.get("homepage") if links else None),
        "model_huggingface": _non_empty_str(
            links.get("huggingface") if links else None
        ),
        "model_civitai": _non_empty_str(links.get("civitai") if links else None),
        "workflow_download_r2_key": workflow_download_r2_key,
        "workflow_download_sha256": workflow_download_sha256,
    }


def _workflow_download_snapshot(
    run_json: dict[str, object],
) -> tuple[list[str], str | None]:
    declared_paths: list[str] = []
    direct_path = _non_empty_str(run_json.get("workflow_download_path"))
    if direct_path is not None:
        declared_paths.append(direct_path)

    config_snapshot = _json_object(run_json.get("config_snapshot"))
    workflow_snapshot = (
        _json_object(config_snapshot.get("workflow")) if config_snapshot else None
    )
    snapshot_path = (
        _non_empty_str(workflow_snapshot.get("download_path"))
        if workflow_snapshot is not None
        else None
    )
    if snapshot_path is not None and snapshot_path not in declared_paths:
        declared_paths.append(snapshot_path)

    expected_sha256 = _non_empty_str(run_json.get("workflow_download_sha256"))
    if expected_sha256 is None and workflow_snapshot is not None:
        expected_sha256 = _non_empty_str(workflow_snapshot.get("download_sha256"))

    return declared_paths, expected_sha256


def _resolve_workflow_download_source(
    run_json: dict[str, object],
) -> tuple[Path | None, str | None, bool]:
    declared_paths, expected_sha256 = _workflow_download_snapshot(run_json)
    if not declared_paths:
        return None, expected_sha256, False

    for declared_path in declared_paths:
        candidate = Path(declared_path)
        if candidate.exists() and candidate.is_file():
            actual_sha256 = _sha256_file(candidate)
            return candidate, actual_sha256, True

    return None, expected_sha256, True


def _build_workflow_download_upload(
    run_json: dict[str, object], *, run_dir_name: str
) -> PlannedUpload | None:
    workflow_path, actual_sha256, declared = _resolve_workflow_download_source(run_json)
    if workflow_path is None:
        if declared:
            raise ValueError("workflow 下载文件不存在")
        return None

    _, expected_sha256 = _workflow_download_snapshot(run_json)
    if expected_sha256 is not None and actual_sha256 is not None:
        if expected_sha256 != actual_sha256:
            raise ValueError(
                f"workflow 下载文件 sha256 校验失败: expected={expected_sha256}, actual={actual_sha256}"
            )

    if actual_sha256 is None:
        raise ValueError("workflow 下载文件缺少 sha256")

    workflow_sha256 = actual_sha256

    return PlannedUpload(
        variant="workflow_download",
        bucket_scope="public",
        key=workflow_object_key(run_dir_name, workflow_sha256),
        content_type="application/json",
        cache_control=cache_control_for("public"),
        byte_size=workflow_path.stat().st_size,
        local_path=workflow_path,
    )


def _build_image_db_fields(metadata_record: dict[str, object]) -> dict[str, object]:
    fields: dict[str, object] = {}

    seed = metadata_record.get("seed")
    if isinstance(seed, int) and not isinstance(seed, bool):
        fields["seed"] = seed

    prompt_hash = _non_empty_str(metadata_record.get("prompt_hash"))
    if prompt_hash is not None:
        fields["prompt_hash"] = prompt_hash

    positive_prompt = _non_empty_str(metadata_record.get("positive_prompt"))
    if positive_prompt is not None:
        fields["positive_prompt"] = positive_prompt

    y_value = _non_empty_str(metadata_record.get("y_value"))
    if y_value is not None:
        fields["y_value"] = y_value

    return fields


def _variant_cache_key(*, bucket: str, r2_key: str) -> str:
    payload = f"v1:{bucket}:{r2_key}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _build_image_variant_db_fields(
    variant_rows: list[dict[str, object]],
) -> dict[str, object]:
    fields: dict[str, object] = {}

    for row in variant_rows:
        variant_name = _non_empty_str(row.get("variant"))
        if variant_name is None or variant_name not in _IMAGE_VARIANTS:
            continue

        bucket = _non_empty_str(row.get("bucket"))
        r2_key = _non_empty_str(row.get("r2_key"))
        if bucket is None or r2_key is None:
            continue

        fields[f"{variant_name}_bucket"] = bucket
        fields[f"{variant_name}_r2_key"] = r2_key
        fields[f"{variant_name}_cache_key"] = _variant_cache_key(
            bucket=bucket,
            r2_key=r2_key,
        )

    return fields


def _assets_from_run_json(run_json: dict[str, object]) -> dict[str, object] | None:
    return _json_object(run_json.get("assets"))


def _resolve_run_asset_source_path(asset: dict[str, object]) -> Path:
    direct_path = _non_empty_str(asset.get("path"))
    if direct_path is not None:
        candidate = Path(direct_path)
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

    repo_relative_path = _non_empty_str(asset.get("repo_relative_path"))
    if repo_relative_path is not None:
        repo_root = Path.cwd().resolve()
        candidate = (repo_root / repo_relative_path).resolve()
        if not candidate.is_relative_to(repo_root):
            raise ValueError(f"run 级静态资源路径越界: {repo_relative_path}")
        if candidate.exists() and candidate.is_file():
            return candidate

    raise ValueError("run 级静态资源文件不存在")


def _resolve_run_asset_source_label(asset: dict[str, object], source_path: Path) -> str:
    repo_relative_path = _non_empty_str(asset.get("repo_relative_path"))
    if repo_relative_path is not None:
        return repo_relative_path
    return source_path.name


def _validate_run_asset_sha256(asset: dict[str, object], *, actual_sha256: str) -> None:
    expected_sha256 = _non_empty_str(asset.get("sha256"))
    if expected_sha256 is not None and expected_sha256 != actual_sha256:
        raise ValueError(
            f"run 级静态资源 sha256 校验失败: expected={expected_sha256}, actual={actual_sha256}"
        )


def _sanitize_run_json_for_persistence(
    run_json: dict[str, object],
) -> dict[str, object]:
    persisted: dict[str, object] = {}
    for key in (
        "run_id",
        "run_key",
        "created_at",
        "dry_run",
        "run_dir",
        "config_schema_version",
        "config_path",
        "config_sha256",
        "x_json_sha256",
        "y_json_sha256",
        "model",
        "template",
        "base_seed",
        "seed_strategy",
        "workflow_api_sha256",
        "workflow_download_sha256",
        "workflow_status",
        "selected_ksampler_node_id",
        "selection",
        "generation_overrides",
        "config_snapshot",
    ):
        value = run_json.get(key)
        if value is not None:
            persisted[key] = copy.deepcopy(value)

    assets = _assets_from_run_json(run_json)
    if assets is not None:
        persisted["assets"] = _sanitize_asset_snapshot(assets)

    return persisted


def _sanitize_asset_snapshot(assets: dict[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    cover_image = _json_object(assets.get("cover_image"))
    if cover_image is not None:
        sanitized_cover = _sanitize_asset_ref(cover_image)
        if sanitized_cover is not None:
            sanitized["cover_image"] = sanitized_cover

    homepage_images = [
        sanitized_asset
        for asset in _json_object_list(assets.get("homepage_images"))
        if (sanitized_asset := _sanitize_asset_ref(asset)) is not None
    ]
    if homepage_images:
        sanitized["homepage_images"] = homepage_images
    return sanitized


def _sanitize_asset_ref(asset: dict[str, object]) -> dict[str, object] | None:
    repo_relative_path = _non_empty_str(asset.get("repo_relative_path"))
    sha256 = _non_empty_str(asset.get("sha256"))
    if repo_relative_path is None and sha256 is None:
        return None

    sanitized: dict[str, object] = {}
    if repo_relative_path is not None:
        sanitized["repo_relative_path"] = repo_relative_path
    if sha256 is not None:
        sanitized["sha256"] = sha256
    return sanitized


def _encoder_params_for_variant(variant: str) -> dict[str, object]:
    if variant == "display_webp":
        return webp_params("display")
    if variant == "thumb_webp":
        return webp_params("thumb")
    if variant == "display_avif":
        return avif_params("display")
    if variant == "thumb_avif":
        return avif_params("thumb")
    raise ValueError(f"unsupported variant: {variant}")


def _source_signature(image_path: Path) -> tuple[str, int, int]:
    resolved_path = image_path.resolve()
    stat_result = resolved_path.stat()
    return str(resolved_path), stat_result.st_size, stat_result.st_mtime_ns


def _source_cache_key(image_path: Path) -> str:
    resolved = str(image_path.resolve()).encode("utf-8")
    return hashlib.sha256(resolved).hexdigest()[:16]


def _variant_lookup_from_rows(
    variant_rows: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for row in variant_rows:
        variant_name = _non_empty_str(row.get("variant"))
        if variant_name is None or variant_name not in _IMAGE_VARIANTS:
            continue
        lookup[variant_name] = dict(row)
    return lookup


def _build_metadata_snapshot(
    *,
    variant_rows: list[dict[str, object]],
    blurhash_value: str | None,
    blurhash_width: int | None = None,
    blurhash_height: int | None = None,
) -> dict[str, object]:
    variant_lookup = _variant_lookup_from_rows(variant_rows)
    display_row = variant_lookup.get("display_webp") or variant_lookup.get(
        "display_avif"
    )
    thumb_row = variant_lookup.get("thumb_webp") or variant_lookup.get("thumb_avif")
    if display_row is None or thumb_row is None:
        raise ValueError("variant rows missing display/thumb metadata")

    display_width = display_row.get("width")
    display_height = display_row.get("height")
    thumb_width = thumb_row.get("width")
    thumb_height = thumb_row.get("height")
    if not all(
        isinstance(value, int)
        for value in (display_width, display_height, thumb_width, thumb_height)
    ):
        raise ValueError("variant rows missing width/height")

    snapshot: dict[str, object] = {
        "display_width": display_width,
        "display_height": display_height,
        "thumb_width": thumb_width,
        "thumb_height": thumb_height,
    }
    if blurhash_value is not None:
        snapshot["blurhash"] = blurhash_value
    if blurhash_width is not None:
        snapshot["blurhash_width"] = blurhash_width
    if blurhash_height is not None:
        snapshot["blurhash_height"] = blurhash_height
    return snapshot


def _build_variant_cache_entry(row: dict[str, object]) -> dict[str, object]:
    variant_name = _non_empty_str(row.get("variant"))
    if variant_name is None or variant_name not in _IMAGE_VARIANTS:
        raise ValueError("variant row missing variant name")

    byte_size = row.get("byte_size")
    sha256 = _non_empty_str(row.get("sha256"))
    width = row.get("width")
    height = row.get("height")
    if not isinstance(byte_size, int) or sha256 is None:
        raise ValueError("variant row missing cache metadata")

    entry: dict[str, object] = {
        "variant": variant_name,
        "byte_size": byte_size,
        "sha256": sha256,
        "encoder_params": _encoder_params_for_variant(variant_name),
    }
    if isinstance(width, int):
        entry["width"] = width
    if isinstance(height, int):
        entry["height"] = height
    return entry


def _write_variant_cache_sidecar(
    *,
    run_intermediate_dir: Path,
    batch_index: int,
    image_path: Path,
    original_sha256: str,
    metadata: dict[str, object],
    variant_rows: list[dict[str, object]],
) -> None:
    source_path, source_size, source_mtime_ns = _source_signature(image_path)
    cache_metadata_path = _intermediate_cache_metadata_path(
        run_intermediate_dir=run_intermediate_dir,
        batch_index=batch_index,
        source_key=_source_cache_key(image_path),
    )
    payload: dict[str, object] = {
        "schema_version": 1,
        "source": {
            "path": source_path,
            "size": source_size,
            "mtime_ns": source_mtime_ns,
            "sha256": original_sha256,
        },
        "metadata": dict(metadata),
        "variants": [_build_variant_cache_entry(row) for row in variant_rows],
    }
    _write_intermediate_cache_metadata(cache_metadata_path, payload)


def _load_cached_variant_bundle(
    *,
    run_intermediate_dir: Path,
    image_path: Path,
    batch_index: int,
) -> _CachedVariantBundle | None:
    cache_metadata_path = _intermediate_cache_metadata_path(
        run_intermediate_dir=run_intermediate_dir,
        batch_index=batch_index,
        source_key=_source_cache_key(image_path),
    )
    payload = _load_intermediate_cache_metadata(cache_metadata_path)
    if payload is None or payload.get("schema_version") != 1:
        return None

    source = _json_object(payload.get("source"))
    metadata = _json_object(payload.get("metadata"))
    if source is None or metadata is None:
        return None

    source_path, source_size, source_mtime_ns = _source_signature(image_path)
    cached_source_path = _non_empty_str(source.get("path"))
    cached_sha256 = _non_empty_str(source.get("sha256"))
    if (
        cached_source_path != source_path
        or not isinstance(source.get("size"), int)
        or not isinstance(source.get("mtime_ns"), int)
        or source.get("size") != source_size
        or source.get("mtime_ns") != source_mtime_ns
        or cached_sha256 is None
    ):
        return None

    cached_variant_paths: dict[str, Path] = {}
    variant_lookup: dict[str, dict[str, object]] = {}
    for row in _json_object_list(payload.get("variants")):
        variant_name = _non_empty_str(row.get("variant"))
        cached_variant_sha256 = _non_empty_str(row.get("sha256"))
        byte_size = row.get("byte_size")
        width = row.get("width")
        height = row.get("height")
        encoder_params = _json_object(row.get("encoder_params"))
        if (
            variant_name is None
            or variant_name not in _IMAGE_VARIANTS
            or cached_variant_sha256 is None
            or not isinstance(byte_size, int)
            or encoder_params != _encoder_params_for_variant(variant_name)
        ):
            return None
        if width is not None and not isinstance(width, int):
            return None
        if height is not None and not isinstance(height, int):
            return None

        variant_path = _intermediate_variant_path(
            run_intermediate_dir=run_intermediate_dir,
            original_sha256=cached_sha256,
            batch_index=batch_index,
            variant=variant_name,
        )
        if not variant_path.exists() or not variant_path.is_file():
            return None
        if variant_path.stat().st_size != byte_size:
            return None

        cached_variant_paths[variant_name] = variant_path
        variant_lookup[variant_name] = dict(row)

    if set(variant_lookup) != set(_DERIVED_IMAGE_VARIANTS):
        return None

    return _CachedVariantBundle(
        original_sha256=cached_sha256,
        metadata=dict(metadata),
        variant_lookup=variant_lookup,
        cached_variant_paths=cached_variant_paths,
    )


def _append_cached_variant_payloads(
    *,
    run_dir_name: str,
    original_sha256: str,
    uploads: list[PlannedUpload],
    variant_rows: list[dict[str, object]],
    cached_variant_paths: dict[str, Path],
    cached_variant_lookup: dict[str, dict[str, object]],
    bucket_scope_for_variant: Callable[[str], BucketScope],
) -> None:
    for variant_name in _DERIVED_IMAGE_VARIANTS:
        cached_row = cached_variant_lookup[variant_name]
        cached_path = cached_variant_paths[variant_name]
        byte_size = cast(int, cached_row["byte_size"])
        scope = bucket_scope_for_variant(variant_name)
        key = object_key(run_dir_name, original_sha256, variant_name)
        upload = _build_variant_upload(
            variant=variant_name,
            bucket_scope=scope,
            key=key,
            byte_size=byte_size,
            local_path=cached_path,
        )
        uploads.append(upload)

        payload: dict[str, object] = {
            "variant": variant_name,
            "bucket": scope,
            "r2_key": key,
            "content_type": upload.content_type,
            "cache_control": upload.cache_control,
            "byte_size": byte_size,
            "sha256": cached_row["sha256"],
        }
        width = cached_row.get("width")
        height = cached_row.get("height")
        if isinstance(width, int):
            payload["width"] = width
        if isinstance(height, int):
            payload["height"] = height
        payload.update(_encoding_fields_for_variant(variant_name))
        variant_rows.append(payload)


def _collect_public_variant_payloads(
    *,
    run_dir_name: str,
    run_intermediate_dir: Path,
    image_path: Path,
    category: Category,
    batch_index: int,
    original_sha256: str,
    uploads: list[PlannedUpload],
    variant_rows: list[dict[str, object]],
    cached_variant_paths: dict[str, Path],
    all_cached: bool,
    cached_bundle: _CachedVariantBundle | None,
    plan_image_variants_fn: Callable[[Path], list[dict[str, object]]],
    inspect_image_metadata_fn: Callable[[Path], dict[str, object]],
) -> tuple[int | None, int | None, str | None, int | None, int | None]:
    blurhash_value: str | None = None
    blurhash_width: int | None = None
    blurhash_height: int | None = None
    width: int | None = None
    height: int | None = None

    if cached_bundle is not None:
        metadata = cached_bundle.metadata
        display_width = cast(int, metadata["display_width"])
        display_height = cast(int, metadata["display_height"])
        thumb_width = cast(int, metadata["thumb_width"])
        thumb_height = cast(int, metadata["thumb_height"])
        blurhash_candidate = metadata.get("blurhash")
        if isinstance(blurhash_candidate, str) and blurhash_candidate:
            blurhash_value = blurhash_candidate
        blurhash_width = cast(int | None, metadata.get("blurhash_width"))
        blurhash_height = cast(int | None, metadata.get("blurhash_height"))
        width = display_width
        height = display_height
        _append_cached_variant_payloads(
            run_dir_name=run_dir_name,
            original_sha256=original_sha256,
            uploads=uploads,
            variant_rows=variant_rows,
            cached_variant_paths=cached_bundle.cached_variant_paths,
            cached_variant_lookup=cached_bundle.variant_lookup,
            bucket_scope_for_variant=lambda variant: bucket_for(category, variant),
        )
        return width, height, blurhash_value, blurhash_width, blurhash_height

    if all_cached:
        metadata = inspect_image_metadata_fn(image_path)
        display_width = cast(int, metadata["display_width"])
        display_height = cast(int, metadata["display_height"])
        thumb_width = cast(int, metadata["thumb_width"])
        thumb_height = cast(int, metadata["thumb_height"])
        blurhash_candidate = metadata.get("blurhash")
        if isinstance(blurhash_candidate, str) and blurhash_candidate:
            blurhash_value = blurhash_candidate
        blurhash_width = cast(int | None, metadata.get("blurhash_width"))
        blurhash_height = cast(int | None, metadata.get("blurhash_height"))
        width = display_width
        height = display_height

        for variant_raw in _DERIVED_IMAGE_VARIANTS:
            intermediate_path = cached_variant_paths[variant_raw]
            key = object_key(run_dir_name, original_sha256, variant_raw)
            upload = _build_variant_upload(
                variant=variant_raw,
                bucket_scope=bucket_for(category, variant_raw),
                key=key,
                byte_size=intermediate_path.stat().st_size,
                local_path=intermediate_path,
            )
            uploads.append(upload)

            row_width = display_width
            row_height = display_height
            if variant_raw in {"thumb_webp", "thumb_avif"}:
                row_width = thumb_width
                row_height = thumb_height

            cached_variant_payload: dict[str, object] = {
                "variant": variant_raw,
                "bucket": bucket_for(category, variant_raw),
                "r2_key": key,
                "content_type": upload.content_type,
                "cache_control": upload.cache_control,
                "byte_size": upload.byte_size,
                "sha256": _sha256_file(intermediate_path),
                "width": row_width,
                "height": row_height,
            }
            cached_variant_payload.update(_encoding_fields_for_variant(variant_raw))
            variant_rows.append(cached_variant_payload)

        _write_variant_cache_sidecar(
            run_intermediate_dir=run_intermediate_dir,
            batch_index=batch_index,
            image_path=image_path,
            original_sha256=original_sha256,
            metadata=dict(metadata),
            variant_rows=variant_rows,
        )

        return width, height, blurhash_value, blurhash_width, blurhash_height

    derived_rows = plan_image_variants_fn(image_path)
    for row in derived_rows:
        kind = row.get("kind")
        if kind == "blurhash":
            value = row.get("value")
            if isinstance(value, str) and value:
                blurhash_value = value
            candidate_width = row.get("hash_width")
            candidate_height = row.get("hash_height")
            if isinstance(candidate_width, int):
                blurhash_width = candidate_width
            if isinstance(candidate_height, int):
                blurhash_height = candidate_height
            continue

        if kind != "image":
            continue

        variant_raw = row.get("variant")
        body_bytes = row.get("bytes")
        row_width = row.get("width")
        row_height = row.get("height")

        if not isinstance(variant_raw, str) or variant_raw not in _IMAGE_VARIANTS:
            continue
        if not isinstance(body_bytes, bytes):
            continue
        if isinstance(row_width, int) and isinstance(row_height, int):
            if width is None:
                width = row_width
            if height is None:
                height = row_height

        intermediate_path, variant_sha256 = _write_intermediate_variant(
            run_intermediate_dir=run_intermediate_dir,
            original_sha256=original_sha256,
            batch_index=batch_index,
            variant=variant_raw,
            body_bytes=body_bytes,
        )
        key = object_key(run_dir_name, original_sha256, variant_raw)
        upload = _build_variant_upload(
            variant=variant_raw,
            bucket_scope=bucket_for(category, variant_raw),
            key=key,
            byte_size=intermediate_path.stat().st_size,
            local_path=intermediate_path,
        )
        uploads.append(upload)
        derived_variant_payload: dict[str, object] = {
            "variant": variant_raw,
            "bucket": bucket_for(category, variant_raw),
            "r2_key": key,
            "content_type": upload.content_type,
            "cache_control": upload.cache_control,
            "byte_size": upload.byte_size,
            "sha256": variant_sha256,
        }
        if isinstance(row_width, int):
            derived_variant_payload["width"] = row_width
        if isinstance(row_height, int):
            derived_variant_payload["height"] = row_height
        derived_variant_payload.update(_encoding_fields_for_variant(variant_raw))
        variant_rows.append(derived_variant_payload)

    _write_variant_cache_sidecar(
        run_intermediate_dir=run_intermediate_dir,
        batch_index=batch_index,
        image_path=image_path,
        original_sha256=original_sha256,
        metadata=_build_metadata_snapshot(
            variant_rows=variant_rows,
            blurhash_value=blurhash_value,
            blurhash_width=blurhash_width,
            blurhash_height=blurhash_height,
        ),
        variant_rows=variant_rows,
    )

    return width, height, blurhash_value, blurhash_width, blurhash_height


def _build_run_asset_payload(
    *,
    run_dir_name: str,
    run_intermediate_dir: Path,
    asset: dict[str, object],
    asset_role: str,
    asset_index: int,
    batch_index: int,
    category: Category,
    plan_image_variants_fn: Callable[
        [Path], list[dict[str, object]]
    ] = plan_image_variants,
    inspect_image_metadata_fn: Callable[
        [Path], dict[str, object]
    ] = inspect_image_metadata,
) -> tuple[dict[str, object], list[PlannedUpload]]:
    source_path = _resolve_run_asset_source_path(asset)
    source_label = _resolve_run_asset_source_label(asset, source_path)

    (
        original_sha256,
        uploads,
        variant_rows,
        cached_variant_paths,
        all_cached,
        cached_bundle,
    ) = _prepare_image_payload_inputs(
        run_dir_name=run_dir_name,
        run_intermediate_dir=run_intermediate_dir,
        image_path=source_path,
        category=category,
        batch_index=batch_index,
    )
    source_sha256 = original_sha256
    _validate_run_asset_sha256(asset, actual_sha256=source_sha256)

    (
        width,
        height,
        blurhash_value,
        blurhash_width,
        blurhash_height,
    ) = _collect_public_variant_payloads(
        run_dir_name=run_dir_name,
        run_intermediate_dir=run_intermediate_dir,
        image_path=source_path,
        category=category,
        batch_index=batch_index,
        original_sha256=original_sha256,
        uploads=uploads,
        variant_rows=variant_rows,
        cached_variant_paths=cached_variant_paths,
        all_cached=all_cached,
        cached_bundle=cached_bundle,
        plan_image_variants_fn=plan_image_variants_fn,
        inspect_image_metadata_fn=inspect_image_metadata_fn,
    )

    payload: dict[str, object] = {
        "asset_role": asset_role,
        "asset_index": asset_index,
        "source_path": source_label,
        "source_sha256": source_sha256,
        "metadata": {
            "repo_relative_path": _non_empty_str(asset.get("repo_relative_path")),
            "source_filename": source_path.name,
        },
        "variants": variant_rows,
    }
    if width is not None:
        payload["width"] = width
    if height is not None:
        payload["height"] = height
    if blurhash_value is not None:
        payload["blurhash"] = blurhash_value
    if blurhash_width is not None:
        payload["blurhash_width"] = blurhash_width
    if blurhash_height is not None:
        payload["blurhash_height"] = blurhash_height
    return payload, uploads


def _build_run_asset_payloads(
    *,
    run_json: dict[str, object],
    run_dir_name: str,
    run_intermediate_dir: Path,
    resolve_asset_category: Callable[[Path], Category],
    plan_image_variants_fn: Callable[
        [Path], list[dict[str, object]]
    ] = plan_image_variants,
    inspect_image_metadata_fn: Callable[
        [Path], dict[str, object]
    ] = inspect_image_metadata,
) -> tuple[list[dict[str, object]], list[PlannedUpload]]:
    assets = _assets_from_run_json(run_json)
    if assets is None:
        return [], []

    asset_rows: list[dict[str, object]] = []
    uploads: list[PlannedUpload] = []
    batch_index = 1_000_000

    cover_image = _json_object(assets.get("cover_image"))
    if cover_image is not None:
        cover_source_path = _resolve_run_asset_source_path(cover_image)
        cover_payload, cover_uploads = _build_run_asset_payload(
            run_dir_name=run_dir_name,
            run_intermediate_dir=run_intermediate_dir,
            asset=cover_image,
            asset_role="cover",
            asset_index=0,
            batch_index=batch_index,
            category=resolve_asset_category(cover_source_path),
            plan_image_variants_fn=plan_image_variants_fn,
            inspect_image_metadata_fn=inspect_image_metadata_fn,
        )
        asset_rows.append(cover_payload)
        uploads.extend(cover_uploads)
        batch_index += 1

    for asset_index, homepage_asset in enumerate(
        _json_object_list(assets.get("homepage_images"))
    ):
        homepage_source_path = _resolve_run_asset_source_path(homepage_asset)
        homepage_payload, homepage_uploads = _build_run_asset_payload(
            run_dir_name=run_dir_name,
            run_intermediate_dir=run_intermediate_dir,
            asset=homepage_asset,
            asset_role="homepage_card",
            asset_index=asset_index,
            batch_index=batch_index,
            category=resolve_asset_category(homepage_source_path),
            plan_image_variants_fn=plan_image_variants_fn,
            inspect_image_metadata_fn=inspect_image_metadata_fn,
        )
        asset_rows.append(homepage_payload)
        uploads.extend(homepage_uploads)
        batch_index += 1

    return asset_rows, uploads


def _merge_asset_category(current: Category, incoming: Category) -> Category:
    if current == "nsfw" or incoming == "nsfw":
        return "nsfw"
    if current == "advance" or incoming == "advance":
        return "advance"
    return "normal"


def _build_run_asset_category_resolver(
    image_tasks: list[PlannedImageTask],
) -> Callable[[Path], Category]:
    path_category: dict[Path, Category] = {}
    sha_category: dict[str, Category] = {}
    for task in image_tasks:
        resolved = task.image_path.resolve()
        existing_path_category = path_category.get(resolved)
        if existing_path_category is None:
            path_category[resolved] = task.category
        else:
            path_category[resolved] = _merge_asset_category(
                existing_path_category, task.category
            )

        sha256 = _sha256_file(resolved)
        existing_sha_category = sha_category.get(sha256)
        if existing_sha_category is None:
            sha_category[sha256] = task.category
        else:
            sha_category[sha256] = _merge_asset_category(
                existing_sha_category, task.category
            )

    def _resolve(path: Path) -> Category:
        resolved = path.resolve()
        by_path = path_category.get(resolved)
        if by_path is not None:
            return by_path
        source_sha256 = _sha256_file(resolved)
        return sha_category.get(source_sha256, _RUN_ASSET_DEFAULT_CATEGORY)

    return _resolve


def _normalize_category(raw_value: object, override: Category | None) -> Category:
    if override is not None:
        return override

    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized == "normal":
            return "normal"
        if normalized == "advance":
            return "advance"
        if normalized == "nsfw":
            return "nsfw"

    return "normal"


def _encoding_fields_for_variant(variant: str) -> dict[str, object]:
    if variant == "display_webp":
        quality = webp_params("display").get("quality")
        return {"webp_quality": quality}
    if variant == "thumb_webp":
        quality = webp_params("thumb").get("quality")
        return {"webp_quality": quality}
    if variant == "display_avif":
        params = avif_params("display")
        return {
            "avif_quality": params.get("quality"),
            "avif_speed": params.get("speed"),
        }
    if variant == "thumb_avif":
        params = avif_params("thumb")
        return {
            "avif_quality": params.get("quality"),
            "avif_speed": params.get("speed"),
        }
    return {}


def _build_variant_upload(
    *,
    variant: str,
    bucket_scope: BucketScope,
    key: str,
    byte_size: int,
    body_bytes: bytes | None = None,
    local_path: Path | None = None,
) -> PlannedUpload:
    if (body_bytes is None) == (local_path is None):
        raise ValueError("exactly one upload source must be provided")

    return PlannedUpload(
        variant=variant,
        bucket_scope=bucket_scope,
        key=key,
        content_type=content_type_for(variant),
        cache_control=cache_control_for(bucket_scope),
        byte_size=byte_size,
        body_bytes=body_bytes,
        local_path=local_path,
    )


def _prepare_image_payload_inputs(
    *,
    run_dir_name: str,
    run_intermediate_dir: Path,
    image_path: Path,
    category: Category,
    batch_index: int,
) -> tuple[
    str,
    list[PlannedUpload],
    list[dict[str, object]],
    dict[str, Path],
    bool,
    _CachedVariantBundle | None,
]:
    uploads: list[PlannedUpload] = []
    variant_rows: list[dict[str, object]] = []

    cached_bundle = _load_cached_variant_bundle(
        run_intermediate_dir=run_intermediate_dir,
        image_path=image_path,
        batch_index=batch_index,
    )
    if cached_bundle is not None:
        return (
            cached_bundle.original_sha256,
            uploads,
            variant_rows,
            dict(cached_bundle.cached_variant_paths),
            True,
            cached_bundle,
        )

    original_sha256 = _sha256_file(image_path)

    cached_variant_paths: dict[str, Path] = {
        variant: _intermediate_variant_path(
            run_intermediate_dir=run_intermediate_dir,
            original_sha256=original_sha256,
            batch_index=batch_index,
            variant=variant,
        )
        for variant in _DERIVED_IMAGE_VARIANTS
    }
    all_cached = all(path.exists() for path in cached_variant_paths.values())
    return (
        original_sha256,
        uploads,
        variant_rows,
        cached_variant_paths,
        all_cached,
        None,
    )


def _collect_derived_variant_payloads(
    *,
    run_dir_name: str,
    run_intermediate_dir: Path,
    image_path: Path,
    category: Category,
    batch_index: int,
    original_sha256: str,
    uploads: list[PlannedUpload],
    variant_rows: list[dict[str, object]],
    cached_variant_paths: dict[str, Path],
    all_cached: bool,
    cached_bundle: _CachedVariantBundle | None,
    plan_image_variants_fn: Callable[[Path], list[dict[str, object]]],
    inspect_image_metadata_fn: Callable[[Path], dict[str, object]],
) -> tuple[int | None, int | None, str | None]:
    blurhash_value: str | None = None
    width: int | None = None
    height: int | None = None

    if cached_bundle is not None:
        metadata = cached_bundle.metadata
        display_width = cast(int, metadata["display_width"])
        display_height = cast(int, metadata["display_height"])
        blurhash_candidate = metadata.get("blurhash")
        if isinstance(blurhash_candidate, str) and blurhash_candidate:
            blurhash_value = blurhash_candidate
        width = display_width
        height = display_height
        _append_cached_variant_payloads(
            run_dir_name=run_dir_name,
            original_sha256=original_sha256,
            uploads=uploads,
            variant_rows=variant_rows,
            cached_variant_paths=cached_bundle.cached_variant_paths,
            cached_variant_lookup=cached_bundle.variant_lookup,
            bucket_scope_for_variant=lambda variant_name: bucket_for(
                category, variant_name
            ),
        )
        return width, height, blurhash_value

    if all_cached:
        metadata = inspect_image_metadata_fn(image_path)
        display_width = cast(int, metadata["display_width"])
        display_height = cast(int, metadata["display_height"])
        thumb_width = cast(int, metadata["thumb_width"])
        thumb_height = cast(int, metadata["thumb_height"])
        blurhash_candidate = metadata.get("blurhash")
        if isinstance(blurhash_candidate, str) and blurhash_candidate:
            blurhash_value = blurhash_candidate
        width = display_width
        height = display_height

        for variant_raw in _DERIVED_IMAGE_VARIANTS:
            intermediate_path = cached_variant_paths[variant_raw]
            scope = bucket_for(category, variant_raw)
            key = object_key(run_dir_name, original_sha256, variant_raw)
            upload = _build_variant_upload(
                variant=variant_raw,
                bucket_scope=scope,
                key=key,
                byte_size=intermediate_path.stat().st_size,
                local_path=intermediate_path,
            )
            uploads.append(upload)

            row_width = display_width
            row_height = display_height
            if variant_raw in {"thumb_webp", "thumb_avif"}:
                row_width = thumb_width
                row_height = thumb_height

            cached_variant_payload: dict[str, object] = {
                "variant": variant_raw,
                "bucket": scope,
                "r2_key": key,
                "content_type": upload.content_type,
                "cache_control": upload.cache_control,
                "byte_size": upload.byte_size,
                "sha256": _sha256_file(intermediate_path),
                "width": row_width,
                "height": row_height,
            }
            cached_variant_payload.update(_encoding_fields_for_variant(variant_raw))
            variant_rows.append(cached_variant_payload)

        _write_variant_cache_sidecar(
            run_intermediate_dir=run_intermediate_dir,
            batch_index=batch_index,
            image_path=image_path,
            original_sha256=original_sha256,
            metadata=dict(metadata),
            variant_rows=variant_rows,
        )

        return width, height, blurhash_value

    derived_rows = plan_image_variants_fn(image_path)
    for row in derived_rows:
        kind = row.get("kind")
        if kind == "blurhash":
            value = row.get("value")
            if isinstance(value, str) and value:
                blurhash_value = value
            continue

        if kind != "image":
            continue

        variant_raw = row.get("variant")
        body_bytes = row.get("bytes")
        row_width = row.get("width")
        row_height = row.get("height")

        if not isinstance(variant_raw, str) or variant_raw not in _IMAGE_VARIANTS:
            continue
        if not isinstance(body_bytes, bytes):
            continue
        if isinstance(row_width, int) and isinstance(row_height, int):
            if width is None:
                width = row_width
            if height is None:
                height = row_height

        intermediate_path, variant_sha256 = _write_intermediate_variant(
            run_intermediate_dir=run_intermediate_dir,
            original_sha256=original_sha256,
            batch_index=batch_index,
            variant=variant_raw,
            body_bytes=body_bytes,
        )
        scope = bucket_for(category, variant_raw)
        key = object_key(run_dir_name, original_sha256, variant_raw)
        upload = _build_variant_upload(
            variant=variant_raw,
            bucket_scope=scope,
            key=key,
            byte_size=intermediate_path.stat().st_size,
            local_path=intermediate_path,
        )
        uploads.append(upload)
        derived_variant_payload: dict[str, object] = {
            "variant": variant_raw,
            "bucket": scope,
            "r2_key": key,
            "content_type": upload.content_type,
            "cache_control": upload.cache_control,
            "byte_size": upload.byte_size,
            "sha256": variant_sha256,
        }
        if isinstance(row_width, int):
            derived_variant_payload["width"] = row_width
        if isinstance(row_height, int):
            derived_variant_payload["height"] = row_height
        derived_variant_payload.update(_encoding_fields_for_variant(variant_raw))
        variant_rows.append(derived_variant_payload)

    _write_variant_cache_sidecar(
        run_intermediate_dir=run_intermediate_dir,
        batch_index=batch_index,
        image_path=image_path,
        original_sha256=original_sha256,
        metadata=_build_metadata_snapshot(
            variant_rows=variant_rows,
            blurhash_value=blurhash_value,
        ),
        variant_rows=variant_rows,
    )

    return width, height, blurhash_value


def _assemble_image_payload(
    *,
    metadata_record: dict[str, object],
    category: Category,
    batch_index: int,
    variant_rows: list[dict[str, object]],
    width: int | None,
    height: int | None,
    blurhash_value: str | None,
) -> dict[str, object]:
    image_payload: dict[str, object] = {
        "x_index": _int_with_default(metadata_record.get("x_index"), default=0),
        "y_index": _int_with_default(metadata_record.get("y_index"), default=0),
        "batch_index": batch_index,
        "category": category,
        "metadata": dict(metadata_record),
        "variants": variant_rows,
    }
    image_payload.update(_build_image_db_fields(metadata_record))
    image_payload.update(_build_image_variant_db_fields(variant_rows))
    if width is not None:
        image_payload["width"] = width
    if height is not None:
        image_payload["height"] = height
    if blurhash_value is not None:
        image_payload["blurhash"] = blurhash_value
    return image_payload


def _build_image_payload(
    *,
    run_dir_name: str,
    run_intermediate_dir: Path,
    image_path: Path,
    metadata_record: dict[str, object],
    category: Category,
    batch_index: int,
    plan_image_variants_fn: Callable[
        [Path], list[dict[str, object]]
    ] = plan_image_variants,
    inspect_image_metadata_fn: Callable[
        [Path], dict[str, object]
    ] = inspect_image_metadata,
) -> tuple[dict[str, object], list[PlannedUpload]]:
    (
        original_sha256,
        uploads,
        variant_rows,
        cached_variant_paths,
        all_cached,
        cached_bundle,
    ) = _prepare_image_payload_inputs(
        run_dir_name=run_dir_name,
        run_intermediate_dir=run_intermediate_dir,
        image_path=image_path,
        category=category,
        batch_index=batch_index,
    )

    width, height, blurhash_value = _collect_derived_variant_payloads(
        run_dir_name=run_dir_name,
        run_intermediate_dir=run_intermediate_dir,
        image_path=image_path,
        category=category,
        batch_index=batch_index,
        original_sha256=original_sha256,
        uploads=uploads,
        variant_rows=variant_rows,
        cached_variant_paths=cached_variant_paths,
        all_cached=all_cached,
        cached_bundle=cached_bundle,
        plan_image_variants_fn=plan_image_variants_fn,
        inspect_image_metadata_fn=inspect_image_metadata_fn,
    )
    image_payload = _assemble_image_payload(
        metadata_record=metadata_record,
        category=category,
        batch_index=batch_index,
        variant_rows=variant_rows,
        width=width,
        height=height,
        blurhash_value=blurhash_value,
    )
    return image_payload, uploads


def _build_run_plan(
    run_dir: Path,
    *,
    intermediate_root: Path,
    category_override: Category | None,
    remaining_limit: int | None,
    image_workers: int,
    on_images_discovered: Callable[[int], None] | None = None,
    on_image_planned: Callable[[], None] | None = None,
    thread_pool_cls: type[ThreadPoolExecutor] = ThreadPoolExecutor,
    plan_image_variants_fn: Callable[
        [Path], list[dict[str, object]]
    ] = plan_image_variants,
    inspect_image_metadata_fn: Callable[
        [Path], dict[str, object]
    ] = inspect_image_metadata,
) -> RunPlan:
    normalized_run_dir = normalize_run_dir(run_dir)
    run_json = _load_run_json(normalized_run_dir)
    run_dir_name = _resolve_run_dir_name(normalized_run_dir, run_json)
    metadata_records = _load_metadata_records(normalized_run_dir)
    run_intermediate_dir = (intermediate_root / run_dir_name).resolve()
    run_intermediate_dir.mkdir(parents=True, exist_ok=True)

    image_tasks: list[PlannedImageTask] = []
    processed_images = 0

    for metadata_record in metadata_records:
        if remaining_limit is not None and processed_images >= remaining_limit:
            break

        image_paths = resolve_metadata_image_paths(normalized_run_dir, metadata_record)
        if not image_paths:
            continue

        base_batch = _int_with_default(metadata_record.get("batch_index"), default=0)
        category = _normalize_category(
            metadata_record.get("x_info_type"), category_override
        )

        for offset, image_path in enumerate(image_paths):
            if remaining_limit is not None and processed_images >= remaining_limit:
                break
            image_tasks.append(
                PlannedImageTask(
                    index=processed_images,
                    image_path=image_path,
                    metadata_record=metadata_record,
                    category=category,
                    batch_index=base_batch + offset,
                )
            )
            processed_images += 1

    if on_images_discovered is not None and image_tasks:
        on_images_discovered(len(image_tasks))

    images_rows: list[dict[str, object]] = []
    image_uploads: list[PlannedUpload] = []
    if image_tasks:
        ordered_results: list[tuple[dict[str, object], list[PlannedUpload]] | None] = [
            None
        ] * len(image_tasks)
        with thread_pool_cls(max_workers=image_workers) as pool:
            future_to_task: dict[
                Future[tuple[dict[str, object], list[PlannedUpload]]], PlannedImageTask
            ] = {
                pool.submit(
                    _build_image_payload,
                    run_dir_name=run_dir_name,
                    run_intermediate_dir=run_intermediate_dir,
                    image_path=task.image_path,
                    metadata_record=task.metadata_record,
                    category=task.category,
                    batch_index=task.batch_index,
                    plan_image_variants_fn=plan_image_variants_fn,
                    inspect_image_metadata_fn=inspect_image_metadata_fn,
                ): task
                for task in image_tasks
            }

            for future in as_completed(future_to_task):
                task = future_to_task[future]
                ordered_results[task.index] = future.result()
                if on_image_planned is not None:
                    on_image_planned()

        for item in ordered_results:
            if item is None:
                raise RuntimeError("missing planned image payload result")
            image_payload, uploads = item
            images_rows.append(image_payload)
            image_uploads.extend(uploads)

    resolve_asset_category = _build_run_asset_category_resolver(image_tasks)
    run_assets_rows, run_asset_uploads = _build_run_asset_payloads(
        run_json=run_json,
        run_dir_name=run_dir_name,
        run_intermediate_dir=run_intermediate_dir,
        resolve_asset_category=resolve_asset_category,
        plan_image_variants_fn=plan_image_variants_fn,
        inspect_image_metadata_fn=inspect_image_metadata_fn,
    )
    image_uploads.extend(run_asset_uploads)

    persisted_run_json = _sanitize_run_json_for_persistence(run_json)

    db_payload: dict[str, object] = {
        "run_dir": run_dir_name,
        "run_json": persisted_run_json,
        "images": images_rows,
        "run_assets": run_assets_rows,
    }
    db_payload.update(_build_run_db_fields(run_json, run_dir_name=run_dir_name))

    workflow_upload = _build_workflow_download_upload(
        run_json, run_dir_name=run_dir_name
    )

    view_release = build_view_release(db_payload)
    db_payload["view_release"] = {
        "schema_version": view_release["schema_version"],
        "release_id": view_release["release_id"],
        "current_r2_key": current_view_object_key(run_dir_name),
        "bootstrap_sfw_r2_key": view_manifest_object_key(
            run_dir_name,
            cast(str, view_release["release_id"]),
            kind="bootstrap",
            viewer_variant="public",
        ),
        "bootstrap_nsfw_r2_key": view_manifest_object_key(
            run_dir_name,
            cast(str, view_release["release_id"]),
            kind="bootstrap",
            viewer_variant="auth_nsfw",
        ),
        "media_access_version": 1,
    }
    db_payload["prompts"] = view_release["prompt_rows"]

    manifest_uploads: list[PlannedUpload] = []

    current_manifest_bytes = _to_json_line(
        cast(dict[str, object], view_release["current_manifest"])
    ).encode("utf-8")
    manifest_uploads.append(
        PlannedUpload(
            variant="view_current",
            bucket_scope="public",
            key=current_view_object_key(run_dir_name),
            content_type="application/json",
            cache_control="public, max-age=60, stale-while-revalidate=300",
            byte_size=len(current_manifest_bytes),
            body_bytes=current_manifest_bytes,
        )
    )

    bootstrap_sfw_bytes = _to_json_line(
        cast(dict[str, object], view_release["bootstrap_sfw"])
    ).encode("utf-8")
    manifest_uploads.append(
        PlannedUpload(
            variant="view_bootstrap_sfw",
            bucket_scope="public",
            key=view_manifest_object_key(
                run_dir_name,
                cast(str, view_release["release_id"]),
                kind="bootstrap",
                viewer_variant="public",
            ),
            content_type="application/json",
            cache_control=cache_control_for("public"),
            byte_size=len(bootstrap_sfw_bytes),
            body_bytes=bootstrap_sfw_bytes,
        )
    )

    bootstrap_nsfw_bytes = _to_json_line(
        cast(dict[str, object], view_release["bootstrap_nsfw"])
    ).encode("utf-8")
    manifest_uploads.append(
        PlannedUpload(
            variant="view_bootstrap_nsfw",
            bucket_scope="private",
            key=view_manifest_object_key(
                run_dir_name,
                cast(str, view_release["release_id"]),
                kind="bootstrap",
                viewer_variant="auth_nsfw",
            ),
            content_type="application/json",
            cache_control=cache_control_for("private"),
            byte_size=len(bootstrap_nsfw_bytes),
            body_bytes=bootstrap_nsfw_bytes,
        )
    )

    row_manifests = cast(
        dict[str, dict[int, dict[str, object]]],
        view_release["row_manifests"],
    )
    for viewer_variant, rows in row_manifests.items():
        bucket_scope: BucketScope = "public" if viewer_variant == "public" else "private"
        cache_control = cache_control_for(bucket_scope)
        for y_index, row_manifest in rows.items():
            row_bytes = _to_json_line(row_manifest).encode("utf-8")
            manifest_uploads.append(
                PlannedUpload(
                    variant=f"view_row_{viewer_variant}",
                    bucket_scope=bucket_scope,
                    key=view_manifest_object_key(
                        run_dir_name,
                        cast(str, view_release["release_id"]),
                        kind="row",
                        viewer_variant=cast(
                            Literal["public", "auth_sfw", "auth_nsfw"],
                            viewer_variant,
                        ),
                        y_index=y_index,
                    ),
                    content_type="application/json",
                    cache_control=cache_control,
                    byte_size=len(row_bytes),
                    body_bytes=row_bytes,
                )
            )

    return RunPlan(
        run_dir=normalized_run_dir,
        run_dir_name=run_dir_name,
        intermediate_dir=run_intermediate_dir,
        processed_images=processed_images,
        upload_index_payload=db_payload,
        image_uploads=image_uploads,
        artifact_uploads=[workflow_upload] if workflow_upload is not None else [],
        manifest_uploads=manifest_uploads,
    )


def _build_plans(
    args: argparse.Namespace,
    *,
    intermediate_root: Path,
    image_workers: int,
    thread_pool_cls: type[ThreadPoolExecutor] = ThreadPoolExecutor,
    plan_image_variants_fn: Callable[
        [Path], list[dict[str, object]]
    ] = plan_image_variants,
    inspect_image_metadata_fn: Callable[
        [Path], dict[str, object]
    ] = inspect_image_metadata,
) -> list[RunPlan]:
    selected_run_dirs = _resolve_selected_run_dirs(args)
    category_override = cast(Category | None, getattr(args, "category", None))
    limit_value = cast(int | None, getattr(args, "limit", None))

    LOG.info(
        "building upload plans: run_count=%s limit=%s intermediate_root=%s image_workers=%s",
        len(selected_run_dirs),
        limit_value,
        intermediate_root,
        image_workers,
    )

    plans: list[RunPlan] = []
    remaining = limit_value
    with logging_redirect_tqdm():
        with tqdm(
            total=0,
            desc="构建计划",
            unit="image",
            dynamic_ncols=True,
        ) as pbar:

            def _grow_image_total(count: int) -> None:
                current_total = pbar.total or 0
                pbar.total = current_total + count
                pbar.refresh()

            def _tick_image_progress() -> None:
                pbar.update(1)

            for run_dir in selected_run_dirs:
                if remaining is not None and remaining <= 0:
                    break
                plan = _build_run_plan(
                    run_dir,
                    intermediate_root=intermediate_root,
                    category_override=category_override,
                    remaining_limit=remaining,
                    image_workers=image_workers,
                    on_images_discovered=_grow_image_total,
                    on_image_planned=_tick_image_progress,
                    thread_pool_cls=thread_pool_cls,
                    plan_image_variants_fn=plan_image_variants_fn,
                    inspect_image_metadata_fn=inspect_image_metadata_fn,
                )
                plans.append(plan)
                if remaining is not None:
                    remaining = max(0, remaining - plan.processed_images)

    LOG.info("upload plans ready: planned_runs=%s", len(plans))

    return plans


def _dry_run_summary(plans: list[RunPlan]) -> dict[str, object]:
    planned_uploads: list[dict[str, object]] = []
    manifest_keys: dict[str, list[str]] = {"public": [], "private": []}
    planned_grid_image_variant_uploads = 0
    planned_run_asset_variant_uploads = 0
    planned_artifact_uploads = 0
    planned_manifest_uploads = 0
    processed_grid_images = 0

    for plan in plans:
        processed_grid_images += plan.processed_images
        images_raw = plan.upload_index_payload.get("images")
        images_list = images_raw if isinstance(images_raw, list) else []
        for image in images_list:
            if not isinstance(image, dict):
                continue
            variants_raw = image.get("variants")
            variants_list = variants_raw if isinstance(variants_raw, list) else []
            planned_grid_image_variant_uploads += len(variants_list)
        run_assets_raw = plan.upload_index_payload.get("run_assets")
        run_assets_list = run_assets_raw if isinstance(run_assets_raw, list) else []
        for run_asset in run_assets_list:
            if not isinstance(run_asset, dict):
                continue
            variants_raw = run_asset.get("variants")
            variants_list = variants_raw if isinstance(variants_raw, list) else []
            planned_run_asset_variant_uploads += len(variants_list)
        for upload in plan.image_uploads:
            planned_uploads.append(upload.to_safe_json())
        for artifact_upload in plan.artifact_uploads:
            planned_artifact_uploads += 1
            planned_uploads.append(artifact_upload.to_safe_json())
        for manifest_upload in plan.manifest_uploads:
            planned_manifest_uploads += 1
            planned_uploads.append(manifest_upload.to_safe_json())
            manifest_keys[manifest_upload.bucket_scope].append(manifest_upload.key)

    return {
        "mode": "dry_run",
        "run_count": len(plans),
        "run_dirs": [plan.run_dir_name for plan in plans],
        "intermediate_dirs": [str(plan.intermediate_dir) for plan in plans],
        "processed_grid_images": processed_grid_images,
        "planned_grid_image_variant_uploads": planned_grid_image_variant_uploads,
        "planned_run_asset_variant_uploads": planned_run_asset_variant_uploads,
        "planned_artifact_uploads": planned_artifact_uploads,
        "planned_manifest_uploads": planned_manifest_uploads,
        "planned_total_uploads": len(planned_uploads),
        "planned_uploads": planned_uploads,
        "manifest_keys": manifest_keys,
    }
