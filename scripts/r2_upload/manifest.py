from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Final, Literal, cast

from scripts.run_naming import validate_run_key


VIEW_SCHEMA_VERSION: Final[int] = 2
ViewerVariant = Literal["public", "auth_sfw", "auth_nsfw"]


def current_view_object_key(run_dir_name: str) -> str:
    normalized_run_dir_name = _validate_run_dir_name(run_dir_name)
    return f"runs/{normalized_run_dir_name}/view/current.json"


def view_manifest_object_key(
    run_dir_name: str,
    release_id: str,
    *,
    kind: Literal["bootstrap", "row"],
    viewer_variant: ViewerVariant,
    y_index: int | None = None,
) -> str:
    normalized_run_dir_name = _validate_run_dir_name(run_dir_name)
    normalized_release_id = _normalize_release_id(release_id)
    if kind == "bootstrap":
        suffix = (
            "bootstrap.sfw.json"
            if viewer_variant in {"public", "auth_sfw"}
            else "bootstrap.nsfw.json"
        )
        return (
            f"runs/{normalized_run_dir_name}/view/v{VIEW_SCHEMA_VERSION}/"
            f"{normalized_release_id}/{suffix}"
        )
    if y_index is None or y_index < 0:
        raise ValueError("row manifest requires non-negative y_index")
    return (
        f"runs/{normalized_run_dir_name}/view/v{VIEW_SCHEMA_VERSION}/"
        f"{normalized_release_id}/rows/{viewer_variant}/{y_index}.json"
    )


def build_view_release(payload: Mapping[str, object]) -> dict[str, object]:
    run_dir = _required_non_empty_str(payload.get("run_dir"), field="run_dir")
    run_json = _required_mapping(payload.get("run_json"), field="run_json")
    images = _required_mapping_list(payload.get("images"), field="images")
    x_columns = _required_sequence(payload.get("x_columns"), field="x_columns")
    y_indexes = _required_int_list(payload.get("y_indexes"), field="y_indexes")

    prompt_rows = _build_prompt_rows(run_dir=run_dir, images=images)
    prompts_by_key = {
        (row["prompt_hash"], row["positive_prompt"]): row for row in prompt_rows
    }
    y_labels = _build_y_labels(y_indexes=y_indexes, images=images)

    run_detail = _build_run_detail(payload=payload, run_json=run_json, y_indexes=y_indexes)

    visible_columns_sfw = _build_visible_columns(x_columns, show_nsfw=False)
    visible_columns_nsfw = _build_visible_columns(x_columns, show_nsfw=True)
    cells_by_y = _group_rows_by_y(images)

    bootstrap_sfw = _build_bootstrap_manifest(
        run_detail=run_detail,
        y_indexes=y_indexes,
        y_labels=y_labels,
        images=images,
        prompts_by_key=prompts_by_key,
        visible_columns=visible_columns_sfw,
        accessible_categories={"normal"},
    )
    bootstrap_nsfw = _build_bootstrap_manifest(
        run_detail=run_detail,
        y_indexes=y_indexes,
        y_labels=y_labels,
        images=images,
        prompts_by_key=prompts_by_key,
        visible_columns=visible_columns_nsfw,
        accessible_categories={"normal", "advance", "nsfw"},
    )

    row_manifests: dict[str, dict[int, dict[str, object]]] = {
        "public": {},
        "auth_sfw": {},
        "auth_nsfw": {},
    }
    for y_index in y_indexes:
        row_images = cells_by_y.get(y_index, [])
        row_manifests["public"][y_index] = _build_row_manifest(
            run_dir=run_dir,
            y_index=y_index,
            images=row_images,
            prompts_by_key=prompts_by_key,
            visible_columns=visible_columns_sfw,
            accessible_categories={"normal"},
        )
        row_manifests["auth_sfw"][y_index] = _build_row_manifest(
            run_dir=run_dir,
            y_index=y_index,
            images=row_images,
            prompts_by_key=prompts_by_key,
            visible_columns=visible_columns_sfw,
            accessible_categories={"normal", "advance"},
        )
        row_manifests["auth_nsfw"][y_index] = _build_row_manifest(
            run_dir=run_dir,
            y_index=y_index,
            images=row_images,
            prompts_by_key=prompts_by_key,
            visible_columns=visible_columns_nsfw,
            accessible_categories={"normal", "advance", "nsfw"},
        )

    release_seed = {
        "bootstrap_sfw": bootstrap_sfw,
        "bootstrap_nsfw": bootstrap_nsfw,
        "row_manifests": row_manifests,
        "prompt_rows": prompt_rows,
    }
    release_id = _manifest_sha256(release_seed)[:20]

    current_manifest = {
        "schema_version": VIEW_SCHEMA_VERSION,
        "run_dir": run_dir,
        "release_id": release_id,
        "bootstrap_sfw_key": view_manifest_object_key(
            run_dir,
            release_id,
            kind="bootstrap",
            viewer_variant="public",
        ),
        "public_row_prefix": (
            f"runs/{run_dir}/view/v{VIEW_SCHEMA_VERSION}/{release_id}/rows/public/"
        ),
    }

    return {
        "schema_version": VIEW_SCHEMA_VERSION,
        "release_id": release_id,
        "current_manifest": current_manifest,
        "bootstrap_sfw": bootstrap_sfw,
        "bootstrap_nsfw": bootstrap_nsfw,
        "row_manifests": row_manifests,
        "prompt_rows": prompt_rows,
    }


def _required_mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _required_sequence(value: object, *, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be a list")
    return cast(Sequence[object], value)


def _required_mapping_list(
    value: object,
    *,
    field: str,
) -> list[Mapping[str, object]]:
    result: list[Mapping[str, object]] = []
    for item in _required_sequence(value, field=field):
        if not isinstance(item, Mapping):
            raise ValueError(f"{field} must contain objects")
        result.append(cast(Mapping[str, object], item))
    return result


def _required_int_list(value: object, *, field: str) -> list[int]:
    result: list[int] = []
    for item in _required_sequence(value, field=field):
        if not isinstance(item, int) or isinstance(item, bool):
            raise ValueError(f"{field} must contain integers")
        result.append(item)
    return result


def _required_non_empty_str(value: object, *, field: str) -> str:
    normalized = _optional_non_empty_str(value)
    if normalized is None:
        raise ValueError(f"{field} must be a non-empty string")
    return normalized


def _optional_non_empty_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _validate_run_dir_name(run_dir_name: str) -> str:
    return validate_run_key(run_dir_name, field_name="run_dir_name")


def _normalize_release_id(release_id: str) -> str:
    trimmed = release_id.strip().lower()
    if not trimmed or any(char not in "0123456789abcdef" for char in trimmed):
        raise ValueError("release_id must be lowercase hex")
    return trimmed


def _manifest_sha256(manifest: Mapping[str, object]) -> str:
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_visible_columns(
    raw_columns: Sequence[object],
    *,
    show_nsfw: bool,
) -> dict[str, object]:
    columns: list[dict[str, object]] = []
    remap: dict[int, int] = {}
    for original_index, raw_column in enumerate(raw_columns):
        if not isinstance(raw_column, Mapping):
            continue
        type_value = _optional_non_empty_str(raw_column.get("type"))
        if not show_nsfw and type_value == "nsfw":
            continue
        description = raw_column.get("description")
        columns.append(
            {
                "type": type_value,
                "description": copy.deepcopy(description)
                if isinstance(description, Mapping)
                else None,
            }
        )
        remap[original_index] = len(columns) - 1
    return {"columns": columns, "remap": remap}


def _build_run_detail(
    *,
    payload: Mapping[str, object],
    run_json: Mapping[str, object],
    y_indexes: list[int],
) -> dict[str, object]:
    model_name = _optional_non_empty_str(payload.get("model_name"))
    model_description_zh = _optional_non_empty_str(payload.get("model_description_zh"))
    model_description_en = _optional_non_empty_str(payload.get("model_description_en"))
    workflow_key = _optional_non_empty_str(payload.get("workflow_download_r2_key"))
    return {
        "run_id": _required_non_empty_str(payload.get("run_id"), field="run_id"),
        "created_at": _required_non_empty_str(
            run_json.get("created_at"),
            field="run_json.created_at",
        ),
        "run_dir": _required_non_empty_str(payload.get("run_dir"), field="run_dir"),
        "selection": {
            "total_cells": int(payload.get("total_cells") or 0),
        },
        "model": {
            "name": model_name,
            "description": {
                "zh": model_description_zh,
                "en": model_description_en,
            },
            "links": {
                "homepage": _optional_non_empty_str(payload.get("model_homepage")),
                "huggingface": _optional_non_empty_str(payload.get("model_huggingface")),
                "civitai": _optional_non_empty_str(payload.get("model_civitai")),
            },
        },
        "workflow": (
            {
                "sha256": _optional_non_empty_str(payload.get("workflow_download_sha256")),
                "download_url": f"/api/comfyui/run/{payload['run_dir']}/workflow",
            }
            if workflow_key is not None
            else None
        ),
        "y_count": len(y_indexes),
    }


def _build_y_labels(
    *,
    y_indexes: list[int],
    images: Sequence[Mapping[str, object]],
) -> list[str]:
    labels_by_index: dict[int, str] = {}
    for image in images:
        y_index = image.get("y_index")
        y_value = _optional_non_empty_str(image.get("y_value"))
        if isinstance(y_index, int) and y_value is not None:
            labels_by_index.setdefault(y_index, y_value)
    return [labels_by_index.get(y_index, "") for y_index in y_indexes]


def _build_prompt_rows(
    *,
    run_dir: str,
    images: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    lookup: dict[tuple[str | None, str], int] = {}
    rows: list[dict[str, object]] = []
    next_id = 1
    for image in images:
        prompt_value = _optional_non_empty_str(image.get("positive_prompt")) or ""
        prompt_hash = _optional_non_empty_str(image.get("prompt_hash"))
        key = (prompt_hash, prompt_value)
        if key in lookup:
            continue
        prompt_id = next_id
        next_id += 1
        lookup[key] = prompt_id
        rows.append(
            {
                "run_dir": run_dir,
                "prompt_id": prompt_id,
                "prompt_hash": prompt_hash,
                "positive_prompt": prompt_value,
            }
        )
    return rows


def _group_rows_by_y(
    images: Sequence[Mapping[str, object]],
) -> dict[int, list[Mapping[str, object]]]:
    grouped: dict[int, list[Mapping[str, object]]] = defaultdict(list)
    for image in images:
        y_index = image.get("y_index")
        if isinstance(y_index, int):
            grouped[y_index].append(image)
    return grouped


def _prompt_row_for_image(
    image: Mapping[str, object],
    prompts_by_key: Mapping[tuple[str | None, str], Mapping[str, object]],
) -> Mapping[str, object]:
    prompt_value = _optional_non_empty_str(image.get("positive_prompt")) or ""
    prompt_hash = _optional_non_empty_str(image.get("prompt_hash"))
    return prompts_by_key[(prompt_hash, prompt_value)]


def _build_bootstrap_manifest(
    *,
    run_detail: Mapping[str, object],
    y_indexes: list[int],
    y_labels: list[str],
    images: Sequence[Mapping[str, object]],
    prompts_by_key: Mapping[tuple[str | None, str], Mapping[str, object]],
    visible_columns: Mapping[str, object],
    accessible_categories: set[str],
) -> dict[str, object]:
    remap = cast(dict[int, int], visible_columns["remap"])
    prompt_ids: set[int] = set()
    blurhash_cells: list[dict[str, object]] = []

    representatives: dict[tuple[int, int], Mapping[str, object]] = {}
    for image in images:
        x_index = image.get("x_index")
        y_index = image.get("y_index")
        batch_index = image.get("batch_index")
        if not isinstance(x_index, int) or not isinstance(y_index, int):
            continue
        if x_index not in remap:
            continue
        if not _is_accessible_category(
            _optional_non_empty_str(image.get("category")),
            accessible_categories=accessible_categories,
        ):
            continue
        prompt_row = _prompt_row_for_image(image, prompts_by_key)
        prompt_ids.add(int(prompt_row["prompt_id"]))
        if not isinstance(batch_index, int):
            continue
        key = (x_index, y_index)
        existing = representatives.get(key)
        if existing is None or int(existing.get("batch_index") or 0) > batch_index:
            representatives[key] = image

    for (original_x_index, y_index), image in sorted(
        representatives.items(),
        key=lambda item: (item[0][1], item[0][0]),
    ):
        prompt_row = _prompt_row_for_image(image, prompts_by_key)
        prompt_id = int(prompt_row["prompt_id"])
        prompt_ids.add(prompt_id)
        blurhash_cells.append(
            {
                "x_index": remap[original_x_index],
                "y_index": y_index,
                "batch_index": int(image.get("batch_index") or 0),
                "category": _optional_non_empty_str(image.get("category")),
                "width": image.get("width"),
                "height": image.get("height"),
                "blurhash": _optional_non_empty_str(image.get("blurhash")),
                "prompt_id": prompt_id,
                "seed": image.get("seed"),
                "prompt_hash": prompt_row["prompt_hash"],
                "y_value": _optional_non_empty_str(image.get("y_value")),
            }
        )

    prompts = [
        {
            "id": int(row["prompt_id"]),
            "prompt_hash": row["prompt_hash"],
            "positive_prompt": row["positive_prompt"],
        }
        for row in sorted(
            (
                cast(Mapping[str, object], row)
                for row in prompts_by_key.values()
                if int(row["prompt_id"]) in prompt_ids
            ),
            key=lambda row: int(row["prompt_id"]),
        )
    ]

    return {
        "schema_version": VIEW_SCHEMA_VERSION,
        "run": copy.deepcopy(run_detail),
        "xLabels": [_build_x_label(column) for column in cast(list[dict[str, object]], visible_columns["columns"])],
        "yLabels": list(y_labels),
        "x_columns": copy.deepcopy(visible_columns["columns"]),
        "y_indexes": list(y_indexes),
        "prompts": prompts,
        "blurhash_cells": blurhash_cells,
    }


def _build_x_label(column: Mapping[str, object]) -> str:
    description = column.get("description")
    if isinstance(description, Mapping):
        zh = _optional_non_empty_str(description.get("zh"))
        if zh is not None:
            return zh
    return ""


def _build_row_manifest(
    *,
    run_dir: str,
    y_index: int,
    images: Sequence[Mapping[str, object]],
    prompts_by_key: Mapping[tuple[str | None, str], Mapping[str, object]],
    visible_columns: Mapping[str, object],
    accessible_categories: set[str],
) -> dict[str, object]:
    remap = cast(dict[int, int], visible_columns["remap"])
    cells_by_x: dict[int, list[dict[str, object]]] = defaultdict(list)

    for image in sorted(
        images,
        key=lambda item: (
            int(item.get("x_index") or 0),
            int(item.get("batch_index") or 0),
        ),
    ):
        original_x_index = image.get("x_index")
        if not isinstance(original_x_index, int) or original_x_index not in remap:
            continue
        category = _optional_non_empty_str(image.get("category"))
        if not _is_accessible_category(
            category,
            accessible_categories=accessible_categories,
        ):
            continue
        prompt_row = _prompt_row_for_image(image, prompts_by_key)
        cells_by_x[remap[original_x_index]].append(
            {
                "batch_index": int(image.get("batch_index") or 0),
                "category": category,
                "width": image.get("width"),
                "height": image.get("height"),
                "blurhash": _optional_non_empty_str(image.get("blurhash")),
                "meta": {
                    "seed": _optional_non_empty_str(image.get("seed")),
                    "prompt_id": int(prompt_row["prompt_id"]),
                    "prompt_hash": prompt_row["prompt_hash"],
                    "positive_prompt": prompt_row["positive_prompt"],
                    "y_value": _optional_non_empty_str(image.get("y_value")),
                },
                "thumb": _build_variant_sources(
                    image,
                    prefix="thumb",
                    allow_variant=category in accessible_categories,
                ),
                "display": _build_variant_sources(
                    image,
                    prefix="display",
                    allow_variant=category in accessible_categories,
                ),
            }
        )

    cells = [
        {
            "x_index": x_index,
            "y_index": y_index,
            "items": items,
        }
        for x_index, items in sorted(cells_by_x.items())
    ]
    return {
        "schema_version": VIEW_SCHEMA_VERSION,
        "run_dir": run_dir,
        "y_index": y_index,
        "cells": cells,
    }


def _build_variant_sources(
    image: Mapping[str, object],
    *,
    prefix: Literal["thumb", "display"],
    allow_variant: bool,
) -> dict[str, object] | None:
    if not allow_variant:
        return None

    result: dict[str, object] = {}
    for format_name in ("webp", "avif"):
        bucket = _optional_non_empty_str(image.get(f"{prefix}_{format_name}_bucket"))
        r2_key = _optional_non_empty_str(image.get(f"{prefix}_{format_name}_r2_key"))
        cache_key = _optional_non_empty_str(image.get(f"{prefix}_{format_name}_cache_key"))
        if bucket is None or r2_key is None or cache_key is None:
            continue
        result[format_name] = {
            "bucket": bucket,
            "cache_key": cache_key,
            "key": r2_key,
        }
    return result or None


def _is_accessible_category(
    category: str | None,
    *,
    accessible_categories: set[str],
) -> bool:
    return category is not None and category in accessible_categories
