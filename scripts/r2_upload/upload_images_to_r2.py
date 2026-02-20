# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from .encoding_params import avif_params, webp_params
from .manifest import build_public_manifest, build_run_manifest, manifest_object_key
from .path_safety import normalize_run_dir, resolve_metadata_image_paths
from .r2_client import R2Client, UploadPlan
from .r2_keys import bucket_for, cache_control_for, content_type_for, object_key
from .supabase_writer import SupabaseWriter
from .variants import plan_image_variants

Category = Literal["normal", "advance", "nsfw"]
BucketScope = Literal["public", "private"]

_RUN_DIR_NAME_RE = re.compile(r"^run-\d{8}T\d{6}Z$")
_CATEGORY_CHOICES: tuple[Category, Category, Category] = (
    "normal",
    "advance",
    "nsfw",
)
_IMAGE_VARIANTS = {
    "original_png",
    "display_webp",
    "display_avif",
    "thumb_webp",
    "thumb_avif",
}

# 退出码映射（稳定约定）：
# - 0: 成功
# - 1: 未分类异常（无 category）
# - 2..9: 已分类错误，便于自动化/CI 精确识别失败原因
_EXIT_CODES_BY_CATEGORY: dict[str, int] = {
    "argument": 2,
    "config": 3,
    "auth": 4,
    "network": 5,
    "rate_limit": 6,
    "retry_exhausted": 7,
    "remote": 8,
    "unexpected": 9,
}


class UploadScriptError(RuntimeError):
    category: str

    def __init__(self, message: str, *, category: str) -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class PlannedUpload:
    variant: str
    bucket_scope: BucketScope
    key: str
    content_type: str
    cache_control: str
    byte_size: int
    body_bytes: bytes

    def to_safe_json(self) -> dict[str, object]:
        return {
            "variant": self.variant,
            "bucket_scope": self.bucket_scope,
            "key": self.key,
            "content_type": self.content_type,
            "cache_control": self.cache_control,
            "byte_size": self.byte_size,
        }


@dataclass(frozen=True)
class RunPlan:
    run_dir: Path
    run_dir_name: str
    processed_images: int
    upload_index_payload: dict[str, object]
    image_uploads: list[PlannedUpload]
    manifest_uploads: list[PlannedUpload]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload ComfyUI run artifacts to R2 + Supabase."
    )
    _ = parser.add_argument(
        "--run-root",
        default="comfyui_api_outputs",
        help="Root directory containing run-* folders.",
    )
    run_group = parser.add_mutually_exclusive_group()
    _ = run_group.add_argument(
        "--run-dir", help="Specific run directory (name or path)."
    )
    _ = run_group.add_argument(
        "--all-runs",
        action="store_true",
        help="Process all runs under --run-root.",
    )
    _ = parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without network or database writes.",
    )
    _ = parser.add_argument(
        "--category",
        choices=["normal", "advance", "nsfw"],
        help="Optional category override.",
    )
    _ = parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Reserved concurrency option.",
    )
    _ = parser.add_argument(
        "--limit",
        type=int,
        help="Reserved limit for number of images.",
    )
    return parser


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _to_json_line(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def _load_run_json(run_dir: Path) -> dict[str, object]:
    run_json_path = run_dir / "run.json"
    raw = run_json_path.read_text(encoding="utf-8")
    parsed = cast(object, json.loads(raw))
    if not isinstance(parsed, dict):
        raise ValueError(f"run.json 必须是对象: {run_json_path}")
    return cast(dict[str, object], parsed)


def _load_metadata_records(run_dir: Path) -> list[dict[str, object]]:
    metadata_path = run_dir / "metadata.jsonl"
    rows: list[dict[str, object]] = []
    for line_number, raw_line in enumerate(
        metadata_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = raw_line.strip()
        if not stripped:
            continue
        parsed = cast(object, json.loads(stripped))
        if not isinstance(parsed, dict):
            raise ValueError(
                f"metadata.jsonl 第 {line_number} 行必须是对象: {metadata_path}"
            )
        rows.append(cast(dict[str, object], parsed))
    return rows


def _is_valid_run_dir(run_dir: Path) -> bool:
    return (
        run_dir.is_dir()
        and (run_dir / "run.json").is_file()
        and (run_dir / "metadata.jsonl").is_file()
        and (run_dir / "images").is_dir()
    )


def _discover_run_dirs(run_root: Path) -> list[Path]:
    if not run_root.exists() or not run_root.is_dir():
        raise FileNotFoundError(f"run_root 不存在或不是目录: {run_root}")

    run_dirs = [
        child.resolve()
        for child in run_root.iterdir()
        if child.is_dir() and _is_valid_run_dir(child)
    ]
    run_dirs.sort(key=lambda item: item.name, reverse=True)
    return run_dirs


def _resolve_single_run_dir(run_root: Path, run_dir_arg: str) -> Path:
    user_path = Path(run_dir_arg)
    if user_path.exists():
        candidate = user_path.resolve()
    else:
        candidate = (run_root / run_dir_arg).resolve()

    if not _is_valid_run_dir(candidate):
        raise FileNotFoundError(
            f"run_dir 必须包含 run.json / metadata.jsonl / images: {candidate}"
        )
    return candidate


def _resolve_selected_run_dirs(args: argparse.Namespace) -> list[Path]:
    run_root = Path(str(args.run_root)).resolve()

    run_dir_arg = getattr(args, "run_dir", None)
    if isinstance(run_dir_arg, str) and run_dir_arg.strip():
        return [_resolve_single_run_dir(run_root, run_dir_arg.strip())]

    if bool(getattr(args, "all_runs", False)):
        return _discover_run_dirs(run_root)

    discovered = _discover_run_dirs(run_root)
    if not discovered:
        raise FileNotFoundError(f"未在 run_root 下发现可用 run: {run_root}")
    return [discovered[0]]


def _resolve_run_dir_name(run_dir: Path, run_json: dict[str, object]) -> str:
    candidate = run_dir.name.strip()
    if _RUN_DIR_NAME_RE.fullmatch(candidate):
        return candidate

    run_json_dir = run_json.get("run_dir")
    if isinstance(run_json_dir, str):
        from_run_json = Path(run_json_dir).name.strip()
        if _RUN_DIR_NAME_RE.fullmatch(from_run_json):
            return from_run_json

    raise ValueError(f"run_dir 名称非法（需要 run-YYYYMMDDTHHMMSSZ）: {run_dir.name}")


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
    body_bytes: bytes,
) -> PlannedUpload:
    return PlannedUpload(
        variant=variant,
        bucket_scope=bucket_scope,
        key=key,
        content_type=content_type_for(variant),
        cache_control=cache_control_for(bucket_scope),
        byte_size=len(body_bytes),
        body_bytes=body_bytes,
    )


def _build_image_payload(
    *,
    run_dir_name: str,
    image_path: Path,
    metadata_record: dict[str, object],
    category: Category,
    batch_index: int,
) -> tuple[dict[str, object], list[PlannedUpload]]:
    original_bytes = image_path.read_bytes()
    original_sha256 = _sha256_hex(original_bytes)

    uploads: list[PlannedUpload] = []
    variant_rows: list[dict[str, object]] = []

    original_variant = "original_png"
    original_scope = bucket_for(category, original_variant)
    original_key = object_key(run_dir_name, original_sha256, original_variant)
    original_upload = _build_variant_upload(
        variant=original_variant,
        bucket_scope=original_scope,
        key=original_key,
        body_bytes=original_bytes,
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

    derived_rows = plan_image_variants(image_path)
    blurhash_value: str | None = None
    width: int | None = None
    height: int | None = None

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

        scope = bucket_for(category, variant_raw)
        key = object_key(run_dir_name, original_sha256, variant_raw)
        upload = _build_variant_upload(
            variant=variant_raw,
            bucket_scope=scope,
            key=key,
            body_bytes=body_bytes,
        )
        uploads.append(upload)

        variant_sha256 = _sha256_hex(body_bytes)
        variant_payload: dict[str, object] = {
            "variant": variant_raw,
            "bucket": scope,
            "r2_key": key,
            "content_type": upload.content_type,
            "cache_control": upload.cache_control,
            "byte_size": upload.byte_size,
            "sha256": variant_sha256,
        }
        if isinstance(row_width, int):
            variant_payload["width"] = row_width
        if isinstance(row_height, int):
            variant_payload["height"] = row_height
        variant_payload.update(_encoding_fields_for_variant(variant_raw))
        variant_rows.append(variant_payload)

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
    category_override: Category | None,
    remaining_limit: int | None,
) -> RunPlan:
    normalized_run_dir = normalize_run_dir(run_dir)
    run_json = _load_run_json(normalized_run_dir)
    run_dir_name = _resolve_run_dir_name(normalized_run_dir, run_json)
    metadata_records = _load_metadata_records(normalized_run_dir)

    images_rows: list[dict[str, object]] = []
    image_uploads: list[PlannedUpload] = []
    processed_images = 0

    for metadata_record in metadata_records:
        if remaining_limit is not None and processed_images >= remaining_limit:
            break

        image_paths = resolve_metadata_image_paths(normalized_run_dir, metadata_record)
        if not image_paths:
            continue

        base_batch = _int_with_default(metadata_record.get("batch_index"), default=0)
        category = _normalize_category(
            metadata_record.get("category"),
            category_override,
        )

        for offset, image_path in enumerate(image_paths):
            if remaining_limit is not None and processed_images >= remaining_limit:
                break

            image_payload, uploads = _build_image_payload(
                run_dir_name=run_dir_name,
                image_path=image_path,
                metadata_record=metadata_record,
                category=category,
                batch_index=base_batch + offset,
            )
            images_rows.append(image_payload)
            image_uploads.extend(uploads)
            processed_images += 1

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
        processed_images=processed_images,
        upload_index_payload=db_payload,
        image_uploads=image_uploads,
        manifest_uploads=manifest_uploads,
    )


def _require_bucket_names() -> dict[BucketScope, str]:
    public_name = os.getenv("R2_PUBLIC_BUCKET")
    private_name = os.getenv("R2_PRIVATE_BUCKET")
    if public_name is None or not public_name.strip():
        raise UploadScriptError(
            "missing required R2 bucket configuration: R2_PUBLIC_BUCKET",
            category="config",
        )
    if private_name is None or not private_name.strip():
        raise UploadScriptError(
            "missing required R2 bucket configuration: R2_PRIVATE_BUCKET",
            category="config",
        )
    return {
        "public": public_name.strip(),
        "private": private_name.strip(),
    }


def _upload_if_missing(
    *,
    r2_client: R2Client,
    bucket_names: dict[BucketScope, str],
    planned: PlannedUpload,
) -> bool:
    bucket_name = bucket_names[planned.bucket_scope]
    if r2_client.head_exists(
        bucket_name,
        planned.key,
        bucket_scope=planned.bucket_scope,
    ):
        return False

    r2_client.upload(
        UploadPlan(
            bucket_name=bucket_name,
            bucket_scope=planned.bucket_scope,
            key=planned.key,
            content_type=planned.content_type,
            cache_control=planned.cache_control,
            body_bytes=planned.body_bytes,
        )
    )
    return True


def _validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    concurrency = int(getattr(args, "concurrency", 1))
    if concurrency < 1:
        parser.error("--concurrency 必须 >= 1")

    limit = getattr(args, "limit", None)
    if limit is not None and int(limit) < 1:
        parser.error("--limit 必须 >= 1")


def _build_plans(args: argparse.Namespace) -> list[RunPlan]:
    selected_run_dirs = _resolve_selected_run_dirs(args)
    category_override = cast(Category | None, getattr(args, "category", None))
    limit_value = cast(int | None, getattr(args, "limit", None))

    plans: list[RunPlan] = []
    remaining = limit_value
    for run_dir in selected_run_dirs:
        if remaining is not None and remaining <= 0:
            break
        plan = _build_run_plan(
            run_dir,
            category_override=category_override,
            remaining_limit=remaining,
        )
        plans.append(plan)
        if remaining is not None:
            remaining = max(0, remaining - plan.processed_images)

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
        "processed_images": processed_images,
        "planned_variants": planned_variants,
        "planned_uploads": planned_uploads,
        "manifest_keys": manifest_keys,
    }


def _execute(plans: list[RunPlan]) -> dict[str, object]:
    bucket_names = _require_bucket_names()
    r2_client = R2Client.from_env(dry_run=False)
    supabase_writer = SupabaseWriter.from_env(dry_run=False)

    uploaded = 0
    skipped_existing = 0
    manifest_uploaded = 0
    processed_images = 0

    for plan in plans:
        processed_images += plan.processed_images

        for upload in plan.image_uploads:
            if _upload_if_missing(
                r2_client=r2_client,
                bucket_names=bucket_names,
                planned=upload,
            ):
                uploaded += 1
            else:
                skipped_existing += 1

        supabase_writer.upsert_upload_index(plan.upload_index_payload)

        for manifest_upload in plan.manifest_uploads:
            if _upload_if_missing(
                r2_client=r2_client,
                bucket_names=bucket_names,
                planned=manifest_upload,
            ):
                manifest_uploaded += 1
            else:
                skipped_existing += 1

    return {
        "mode": "execute",
        "run_count": len(plans),
        "run_dirs": [plan.run_dir_name for plan in plans],
        "processed_images": processed_images,
        "uploaded": uploaded,
        "skipped_existing": skipped_existing,
        "db_upserts": len(plans),
        "manifest_uploaded": manifest_uploaded,
    }


def _exit_code_for_exception(exc: Exception) -> int:
    category = getattr(exc, "category", None)
    if isinstance(category, str):
        return _EXIT_CODES_BY_CATEGORY.get(category, 1)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        _validate_args(args, parser)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 1

    try:
        plans = _build_plans(args)
        dry_run = bool(getattr(args, "dry_run", False))

        if dry_run:
            print(_to_json_line(_dry_run_summary(plans)))
            return 0

        print(_to_json_line(_execute(plans)))
        return 0
    except Exception as exc:
        category = getattr(exc, "category", None)
        exit_code = _exit_code_for_exception(exc)
        error_payload = {
            "mode": "error",
            "error": exc.__class__.__name__,
            "message": str(exc),
            "exit_code": exit_code,
        }
        if isinstance(category, str):
            error_payload["category"] = category
        print(_to_json_line(error_payload))
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
