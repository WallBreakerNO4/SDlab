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
    public_manifest["run_json"] = _public_run_json(private_manifest.get("run_json"))
    public_manifest["images"] = _public_images(private_manifest.get("images"))
    public_manifest["run_assets"] = _public_run_assets(
        private_manifest.get("run_assets")
    )
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


def _public_run_assets(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []

    result: list[dict[str, object]] = []
    for run_asset_obj in value:
        if not isinstance(run_asset_obj, Mapping):
            continue
        run_asset_mapping = cast(Mapping[str, object], run_asset_obj)
        run_asset = _clone_mapping(run_asset_mapping)
        run_asset["variants"] = _public_variants(run_asset_mapping.get("variants"))
        result.append(run_asset)
    return result


def _public_run_json(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}

    run_json = cast(Mapping[str, object], value)
    result: dict[str, object] = {}
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
        "workflow_json_sha256",
        "workflow_download_sha256",
        "workflow_status",
        "selected_ksampler_node_id",
        "selection",
        "generation_overrides",
        "config_snapshot",
    ):
        raw = run_json.get(key)
        if raw is not None:
            result[key] = copy.deepcopy(raw)
    assets = _public_asset_snapshot(run_json.get("assets"))
    if assets:
        result["assets"] = assets
    return result


def _public_asset_snapshot(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}

    assets = cast(Mapping[str, object], value)
    result: dict[str, object] = {}
    cover_image = _public_asset_ref(assets.get("cover_image"))
    if cover_image is not None:
        result["cover_image"] = cover_image

    homepage_images = [
        asset
        for raw in cast(Sequence[object], assets.get("homepage_images", []))
        if (asset := _public_asset_ref(raw)) is not None
    ]
    if homepage_images:
        result["homepage_images"] = homepage_images
    return result


def _public_asset_ref(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None

    asset = cast(Mapping[str, object], value)
    result: dict[str, object] = {}
    repo_relative_path = asset.get("repo_relative_path")
    sha256 = asset.get("sha256")
    if isinstance(repo_relative_path, str) and repo_relative_path:
        result["repo_relative_path"] = repo_relative_path
    if isinstance(sha256, str) and sha256:
        result["sha256"] = sha256
    return result if result else None


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
