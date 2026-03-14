# pyright: basic

from __future__ import annotations

import re
from typing import Final, Literal, cast

from scripts.run_naming import validate_run_key

VariantId = Literal[
    "display_webp",
    "display_avif",
    "thumb_webp",
    "thumb_avif",
]

BucketName = Literal["public", "private"]

_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]{64}$")

_VARIANT_EXT: Final[dict[VariantId, str]] = {
    "display_webp": "webp",
    "display_avif": "avif",
    "thumb_webp": "webp",
    "thumb_avif": "avif",
}

_VARIANT_CONTENT_TYPE: Final[dict[VariantId, str]] = {
    "display_webp": "image/webp",
    "display_avif": "image/avif",
    "thumb_webp": "image/webp",
    "thumb_avif": "image/avif",
}

_CACHE_CONTROL_BY_BUCKET: Final[dict[BucketName, str]] = {
    "public": "public, max-age=31536000, immutable",
    "private": "private, max-age=0, no-cache",
}

_PUBLIC_VARIANTS: Final[set[VariantId]] = {
    "display_webp",
    "display_avif",
    "thumb_webp",
    "thumb_avif",
}


def _normalize_category(category: str) -> str:
    normalized = category.strip().lower()
    if normalized not in {"normal", "advance", "nsfw"}:
        raise ValueError(f"不支持的 category: {category}")
    return normalized


def _normalize_variant(variant: str) -> VariantId:
    if variant not in _VARIANT_EXT:
        raise ValueError(f"不支持的 variant: {variant}")
    return cast(VariantId, variant)


def _validate_run_dir_name(run_dir_name: str) -> str:
    return validate_run_key(run_dir_name, field_name="run_dir_name")


def _normalize_image_sha256(image_sha256: str) -> str:
    normalized = image_sha256.strip().lower()
    if not _SHA256_RE.fullmatch(normalized):
        raise ValueError("image_sha256 必须是 64 位十六进制字符串")
    return normalized


def bucket_for(category: str, variant: str) -> BucketName:
    normalized_category = _normalize_category(category)
    normalized_variant = _normalize_variant(variant)

    if normalized_category == "normal" and normalized_variant in _PUBLIC_VARIANTS:
        return "public"
    return "private"


def content_type_for(variant: str) -> str:
    normalized_variant = _normalize_variant(variant)
    return _VARIANT_CONTENT_TYPE[normalized_variant]


def cache_control_for(bucket: str) -> str:
    if bucket not in _CACHE_CONTROL_BY_BUCKET:
        raise ValueError(f"不支持的 bucket: {bucket}")
    return _CACHE_CONTROL_BY_BUCKET[bucket]


def object_key(run_dir_name: str, image_sha256: str, variant: str) -> str:
    normalized_run_dir_name = _validate_run_dir_name(run_dir_name)
    normalized_sha256 = _normalize_image_sha256(image_sha256)
    normalized_variant = _normalize_variant(variant)
    ext = _VARIANT_EXT[normalized_variant]

    return (
        f"runs/{normalized_run_dir_name}/"
        f"sha256/{normalized_sha256[:2]}/{normalized_sha256}/"
        f"{normalized_variant}.{ext}"
    )
