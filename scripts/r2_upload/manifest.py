from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Final, Literal, cast

from scripts.run_naming import validate_run_key


SCHEMA_VERSION: Final[int] = 1
_VISIBILITY_VALUES: Final[set[str]] = {"public", "private"}


def build_run_manifest(payload: dict[str, object]) -> dict[str, object]:
    manifest = copy.deepcopy(payload)
    manifest["schema_version"] = SCHEMA_VERSION
    return manifest


def build_public_manifest(private_manifest: Mapping[str, object]) -> dict[str, object]:
    public_manifest = _clone_mapping(private_manifest)
    public_manifest["schema_version"] = _normalize_schema_version(
        private_manifest.get("schema_version")
    )
    public_manifest["images"] = _public_images(private_manifest.get("images"))
    return public_manifest


def manifest_object_key(
    run_dir_name: str,
    manifest: Mapping[str, object],
    *,
    visibility: Literal["public", "private"],
) -> str:
    normalized_run_dir_name = _validate_run_dir_name(run_dir_name)
    normalized_visibility = _normalize_visibility(visibility)
    schema_version = _schema_version_segment(manifest)
    digest = _manifest_sha256(manifest)
    return (
        f"manifests/{normalized_visibility}/"
        f"runs/{normalized_run_dir_name}/"
        f"schema/{schema_version}/"
        f"{digest}.json"
    )


def _clone_mapping(data: Mapping[str, object]) -> dict[str, object]:
    return {key: copy.deepcopy(value) for key, value in data.items()}


def _public_images(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []

    result: list[dict[str, object]] = []
    for image_obj in value:
        if not isinstance(image_obj, Mapping):
            continue
        image_mapping = cast(Mapping[str, object], image_obj)
        category = image_mapping.get("category")
        if not isinstance(category, str) or category.strip().lower() != "normal":
            continue

        image = _clone_mapping(image_mapping)
        image["variants"] = _public_variants(image_mapping.get("variants"))
        result.append(image)
    return result


def _public_variants(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []

    result: list[dict[str, object]] = []
    for variant_obj in value:
        if not isinstance(variant_obj, Mapping):
            continue
        variant_mapping = cast(Mapping[str, object], variant_obj)
        bucket = variant_mapping.get("bucket")
        if not isinstance(bucket, str) or bucket.strip().lower() != "public":
            continue
        result.append(_clone_mapping(variant_mapping))
    return result


def _manifest_sha256(manifest: Mapping[str, object]) -> str:
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_visibility(visibility: str) -> str:
    normalized = visibility.strip().lower()
    if normalized not in _VISIBILITY_VALUES:
        raise ValueError(f"不支持的 visibility: {visibility}")
    return normalized


def _validate_run_dir_name(run_dir_name: str) -> str:
    return validate_run_key(run_dir_name, field_name="run_dir_name")


def _normalize_schema_version(raw: object) -> int | str:
    if raw is None:
        return SCHEMA_VERSION
    if isinstance(raw, bool):
        raise ValueError("schema_version 不支持 bool")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        normalized = raw.strip()
        if not normalized:
            raise ValueError("schema_version 不能为空字符串")
        return normalized
    raise ValueError("schema_version 必须是 int 或非空字符串")


def _schema_version_segment(manifest: Mapping[str, object]) -> str:
    value = _normalize_schema_version(manifest.get("schema_version"))
    return str(value)
