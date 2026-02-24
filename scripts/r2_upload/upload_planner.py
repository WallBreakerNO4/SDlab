# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import cast

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from .encoding_params import avif_params, webp_params
from .manifest import build_public_manifest, build_run_manifest, manifest_object_key
from .path_safety import normalize_run_dir, resolve_metadata_image_paths
from .r2_keys import bucket_for, cache_control_for, content_type_for, object_key
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
    _intermediate_variant_path,
    _load_metadata_records,
    _load_run_json,
    _sha256_file,
    _to_json_line,
    _write_intermediate_variant,
)
from .variants import inspect_image_metadata, plan_image_variants

LOG = logging.getLogger(__name__)


def _int_with_default(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


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
    original_sha256 = _sha256_file(image_path)

    uploads: list[PlannedUpload] = []
    variant_rows: list[dict[str, object]] = []

    original_variant = "original_png"
    original_scope = bucket_for(category, original_variant)
    original_key = object_key(run_dir_name, original_sha256, original_variant)
    original_upload = _build_variant_upload(
        variant=original_variant,
        bucket_scope=original_scope,
        key=original_key,
        byte_size=image_path.stat().st_size,
        local_path=image_path,
    )
    uploads.append(original_upload)
    variant_rows.append(
        {
            "variant": original_variant,
            "bucket": original_scope,
            "r2_key": original_key,
            "content_type": original_upload.content_type,
            "cache_control": original_upload.cache_control,
            "byte_size": original_upload.byte_size,
            "sha256": original_sha256,
        }
    )

    blurhash_value: str | None = None
    width: int | None = None
    height: int | None = None

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
    else:
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

    image_payload: dict[str, object] = {
        "x_index": _int_with_default(metadata_record.get("x_index"), default=0),
        "y_index": _int_with_default(metadata_record.get("y_index"), default=0),
        "batch_index": batch_index,
        "category": category,
        "metadata": dict(metadata_record),
        "variants": variant_rows,
    }
    if width is not None:
        image_payload["width"] = width
    if height is not None:
        image_payload["height"] = height
    if blurhash_value is not None:
        image_payload["blurhash"] = blurhash_value

    return image_payload, uploads


def _build_run_plan(
    run_dir: Path,
    *,
    intermediate_root: Path,
    category_override: Category | None,
    remaining_limit: int | None,
    image_workers: int,
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
            metadata_record.get("category"), category_override
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

    db_payload: dict[str, object] = {
        "run_dir": run_dir_name,
        "run_json": run_json,
        "images": images_rows,
    }

    private_manifest = build_run_manifest(db_payload)
    public_manifest = build_public_manifest(private_manifest)
    private_manifest_bytes = _to_json_line(private_manifest).encode("utf-8")
    public_manifest_bytes = _to_json_line(public_manifest).encode("utf-8")

    private_manifest_key = manifest_object_key(
        run_dir_name,
        private_manifest,
        visibility="private",
    )
    public_manifest_key = manifest_object_key(
        run_dir_name,
        public_manifest,
        visibility="public",
    )

    manifest_uploads = [
        PlannedUpload(
            variant="manifest_private",
            bucket_scope="private",
            key=private_manifest_key,
            content_type="application/json",
            cache_control=cache_control_for("private"),
            byte_size=len(private_manifest_bytes),
            body_bytes=private_manifest_bytes,
        ),
        PlannedUpload(
            variant="manifest_public",
            bucket_scope="public",
            key=public_manifest_key,
            content_type="application/json",
            cache_control=cache_control_for("public"),
            byte_size=len(public_manifest_bytes),
            body_bytes=public_manifest_bytes,
        ),
    ]

    return RunPlan(
        run_dir=normalized_run_dir,
        run_dir_name=run_dir_name,
        intermediate_dir=run_intermediate_dir,
        processed_images=processed_images,
        upload_index_payload=db_payload,
        image_uploads=image_uploads,
        manifest_uploads=manifest_uploads,
    )


def _estimate_image_count_for_run(run_dir: Path, *, remaining_limit: int | None) -> int:
    normalized_run_dir = normalize_run_dir(run_dir)
    metadata_records = _load_metadata_records(normalized_run_dir)
    estimated_images = 0

    for metadata_record in metadata_records:
        if remaining_limit is not None and estimated_images >= remaining_limit:
            break

        image_paths = resolve_metadata_image_paths(normalized_run_dir, metadata_record)
        if not image_paths:
            continue

        allowed = len(image_paths)
        if remaining_limit is not None:
            allowed = min(allowed, remaining_limit - estimated_images)
        estimated_images += allowed

    return estimated_images


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

    remaining_for_estimate = limit_value
    estimated_images = 0
    for run_dir in selected_run_dirs:
        if remaining_for_estimate is not None and remaining_for_estimate <= 0:
            break
        estimated_for_run = _estimate_image_count_for_run(
            run_dir,
            remaining_limit=remaining_for_estimate,
        )
        estimated_images += estimated_for_run
        if remaining_for_estimate is not None:
            remaining_for_estimate = max(0, remaining_for_estimate - estimated_for_run)

    LOG.info(
        "building upload plans: run_count=%s estimated_images=%s limit=%s intermediate_root=%s image_workers=%s",
        len(selected_run_dirs),
        estimated_images,
        limit_value,
        intermediate_root,
        image_workers,
    )

    plans: list[RunPlan] = []
    remaining = limit_value
    with logging_redirect_tqdm():
        with tqdm(
            total=estimated_images,
            desc="构建计划",
            unit="image",
            dynamic_ncols=True,
        ) as pbar:

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
    planned_variants = 0
    processed_images = 0

    for plan in plans:
        processed_images += plan.processed_images
        planned_variants += len(plan.image_uploads)
        for upload in plan.image_uploads:
            planned_uploads.append(upload.to_safe_json())
        for manifest_upload in plan.manifest_uploads:
            planned_uploads.append(manifest_upload.to_safe_json())
            manifest_keys[manifest_upload.bucket_scope].append(manifest_upload.key)

    return {
        "mode": "dry_run",
        "run_count": len(plans),
        "run_dirs": [plan.run_dir_name for plan in plans],
        "intermediate_dirs": [str(plan.intermediate_dir) for plan in plans],
        "processed_images": processed_images,
        "planned_variants": planned_variants,
        "planned_uploads": planned_uploads,
        "manifest_keys": manifest_keys,
    }
