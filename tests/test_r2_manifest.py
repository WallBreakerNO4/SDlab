# pyright: basic, reportMissingImports=false

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Literal, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.manifest import (
    VIEW_SCHEMA_VERSION,
    build_view_release,
    current_view_object_key,
    view_manifest_object_key,
)


def _sample_payload() -> dict[str, object]:
    return {
        "run_dir": "chenkinnoob-xl-rf",
        "run_id": "chenkinnoob-xl-rf",
        "run_json": {
            "run_id": "chenkinnoob-xl-rf",
            "created_at": "2025-01-01T00:00:00Z",
        },
        "images": [
            {
                "x_index": 0,
                "y_index": 0,
                "batch_index": 0,
                "category": "normal",
                "positive_prompt": "a beautiful landscape",
                "prompt_hash": "p1",
                "width": 1024,
                "height": 1024,
                "blurhash": "L6PZfSi_.AyE_3t7t7R**0o#DgR4",
                "seed": "111",
                "y_value": "cfg_7.0",
                "thumb_webp_bucket": "public",
                "thumb_webp_r2_key": "runs/public/normal-thumb.webp",
                "thumb_webp_cache_key": "ck1",
                "display_webp_bucket": "public",
                "display_webp_r2_key": "runs/public/normal-display.webp",
                "display_webp_cache_key": "ck2",
            },
            {
                "x_index": 1,
                "y_index": 0,
                "batch_index": 0,
                "category": "nsfw",
                "positive_prompt": "a beautiful landscape",
                "prompt_hash": "p1",
                "width": 1024,
                "height": 1024,
                "blurhash": "L6PZfSi_.AyE_3t7t7R**0o#DgR4",
                "seed": "222",
                "y_value": "cfg_7.0",
                "thumb_webp_bucket": "private",
                "thumb_webp_r2_key": "runs/private/nsfw-thumb.webp",
                "thumb_webp_cache_key": "ck3",
                "display_webp_bucket": "private",
                "display_webp_r2_key": "runs/private/nsfw-display.webp",
                "display_webp_cache_key": "ck4",
            },
        ],
        "x_columns": [
            {"type": "normal", "description": {"zh": "\u666e\u901a"}},
            {"type": "nsfw", "description": {"zh": "\u654f\u611f"}},
        ],
        "y_indexes": [0],
        "total_cells": 2,
    }


# ---- build_view_release ----

def test_build_view_release_includes_schema_version() -> None:
    release = build_view_release(_sample_payload())

    assert release["schema_version"] == VIEW_SCHEMA_VERSION


def test_build_view_release_produces_expected_keys() -> None:
    release = build_view_release(_sample_payload())

    assert "release_id" in release
    assert "current_manifest" in release
    assert "bootstrap_sfw" in release
    assert "bootstrap_nsfw" in release
    assert "row_manifests" in release
    assert "prompt_rows" in release


def test_build_view_release_isolation() -> None:
    payload = _sample_payload()
    release = build_view_release(payload)

    images = cast(list[dict[str, object]], release["bootstrap_sfw"]["blurhash_cells"])
    assert len(images) > 0
    images[0]["category"] = "advance"

    payload_images = cast(list[dict[str, object]], payload["images"])
    assert payload_images[0]["category"] == "normal"


def test_release_id_is_stable() -> None:
    release1 = build_view_release(_sample_payload())
    release2 = build_view_release(_sample_payload())

    assert release1["release_id"] == release2["release_id"]


def test_release_id_changes_with_content() -> None:
    payload = _sample_payload()
    release1 = build_view_release(payload)

    payload2 = copy.deepcopy(payload)
    images = cast(list[dict[str, object]], payload2["images"])
    images[0]["x_index"] = 999

    release2 = build_view_release(payload2)
    assert release1["release_id"] != release2["release_id"]


# ---- bootstrap sfw / nsfw ----

def test_sfw_bootstrap_only_has_normal_cells() -> None:
    release = build_view_release(_sample_payload())

    cells = cast(list[dict[str, object]], release["bootstrap_sfw"]["blurhash_cells"])
    assert len(cells) == 1
    assert cells[0]["category"] == "normal"


def test_nsfw_bootstrap_has_all_cells() -> None:
    release = build_view_release(_sample_payload())

    cells = cast(list[dict[str, object]], release["bootstrap_nsfw"]["blurhash_cells"])
    assert len(cells) == 2
    categories = {cast(str, cell["category"]) for cell in cells}
    assert categories == {"normal", "nsfw"}


def test_both_bootstraps_include_prompts() -> None:
    release = build_view_release(_sample_payload())

    for key in ("bootstrap_sfw", "bootstrap_nsfw"):
        prompts = cast(list[dict[str, object]], release[key]["prompts"])
        assert len(prompts) >= 1
        assert "positive_prompt" in prompts[0]
        assert "prompt_hash" in prompts[0]
        assert "id" in prompts[0]


def test_both_bootstraps_include_run_detail() -> None:
    release = build_view_release(_sample_payload())

    for key in ("bootstrap_sfw", "bootstrap_nsfw"):
        run = cast(dict[str, object], release[key]["run"])
        assert run["run_id"] == "chenkinnoob-xl-rf"
        assert run["run_dir"] == "chenkinnoob-xl-rf"


# ---- row_manifests (viewer variants) ----

def test_public_row_only_has_normal_category() -> None:
    release = build_view_release(_sample_payload())

    public_rows = cast(dict[str, object], release["row_manifests"]["public"])
    row = cast(dict[str, object], public_rows[0])
    cells = cast(list[dict[str, object]], row["cells"])

    for cell in cells:
        items = cast(list[dict[str, object]], cell["items"])
        for item in items:
            assert item["category"] == "normal"


def test_auth_sfw_row_has_normal_and_advance() -> None:
    release = build_view_release(_sample_payload())

    sfw_rows = cast(dict[str, object], release["row_manifests"]["auth_sfw"])
    row = cast(dict[str, object], sfw_rows[0])
    cells = cast(list[dict[str, object]], row["cells"])

    categories: set[str] = set()
    for cell in cells:
        for item in cast(list[dict[str, object]], cell["items"]):
            categories.add(cast(str, item["category"]))
    # Our sample has normal+nsfw, so sfw should only see normal
    assert categories == {"normal"}


def test_auth_nsfw_row_has_all_categories() -> None:
    release = build_view_release(_sample_payload())

    nsfw_rows = cast(dict[str, object], release["row_manifests"]["auth_nsfw"])
    row = cast(dict[str, object], nsfw_rows[0])
    cells = cast(list[dict[str, object]], row["cells"])

    categories: set[str] = set()
    for cell in cells:
        for item in cast(list[dict[str, object]], cell["items"]):
            categories.add(cast(str, item["category"]))
    assert categories == {"normal", "nsfw"}


def test_public_row_variant_sources_not_leaked() -> None:
    release = build_view_release(_sample_payload())

    public_rows = cast(dict[str, object], release["row_manifests"]["public"])
    row = cast(dict[str, object], public_rows[0])
    cells = cast(list[dict[str, object]], row["cells"])

    for cell in cells:
        for item in cast(list[dict[str, object]], cell["items"]):
            thumb = item.get("thumb")
            display = item.get("display")
            if thumb is not None:
                thumb_dict = cast(dict[str, object], thumb)
                for fmt_name in ("webp", "avif"):
                    variant = thumb_dict.get(fmt_name)
                    if variant is not None:
                        variant_dict = cast(dict[str, object], variant)
                        assert variant_dict["bucket"] == "public"
                        assert "private" not in cast(str, variant_dict["key"])
            if display is not None:
                display_dict = cast(dict[str, object], display)
                for fmt_name in ("webp", "avif"):
                    variant = display_dict.get(fmt_name)
                    if variant is not None:
                        variant_dict = cast(dict[str, object], variant)
                        assert variant_dict["bucket"] == "public"
                        assert "private" not in cast(str, variant_dict["key"])


# ---- view_manifest_object_key ----

def test_view_manifest_object_key_stable_and_format() -> None:
    key1 = view_manifest_object_key(
        "chenkinnoob-xl-rf",
        "abc123def456",
        kind="bootstrap",
        viewer_variant="public",
    )
    key2 = view_manifest_object_key(
        "chenkinnoob-xl-rf",
        "abc123def456",
        kind="bootstrap",
        viewer_variant="public",
    )

    assert key1 == key2
    assert key1.startswith("runs/chenkinnoob-xl-rf/view/v2/abc123def456/")
    assert "bootstrap.sfw.json" in key1


def test_view_manifest_object_key_nsfw_variant() -> None:
    key = view_manifest_object_key(
        "chenkinnoob-xl-rf",
        "abc123def456",
        kind="bootstrap",
        viewer_variant="auth_nsfw",
    )

    assert "bootstrap.nsfw.json" in key


def test_view_manifest_object_key_row_format() -> None:
    key = view_manifest_object_key(
        "chenkinnoob-xl-rf",
        "abc123def456",
        kind="row",
        viewer_variant="public",
        y_index=3,
    )

    assert key.startswith("runs/chenkinnoob-xl-rf/view/v2/abc123def456/rows/public/")
    assert key.endswith("3.json")


def test_view_manifest_object_key_rejects_invalid_run_dir() -> None:
    with pytest.raises(ValueError, match="run_dir_name"):
        view_manifest_object_key(
            "RUN_NAME",
            "abc",
            kind="bootstrap",
            viewer_variant="public",
        )


def test_view_manifest_object_key_rejects_invalid_release_id() -> None:
    with pytest.raises(ValueError, match="release_id"):
        view_manifest_object_key(
            "chenkinnoob-xl-rf",
            "INVALID_ID!!",
            kind="bootstrap",
            viewer_variant="public",
        )


def test_view_manifest_object_key_rejects_negative_y_index() -> None:
    with pytest.raises(ValueError, match="y_index"):
        view_manifest_object_key(
            "chenkinnoob-xl-rf",
            "abc",
            kind="row",
            viewer_variant="public",
            y_index=-1,
        )


def test_view_manifest_object_key_rejects_missing_y_index_for_row() -> None:
    with pytest.raises(ValueError, match="y_index"):
        view_manifest_object_key(
            "chenkinnoob-xl-rf",
            "abc",
            kind="row",
            viewer_variant="public",
        )


# ---- current_view_object_key ----

def test_current_view_object_key_format() -> None:
    key = current_view_object_key("chenkinnoob-xl-rf")

    assert key == "runs/chenkinnoob-xl-rf/view/current.json"


def test_current_view_object_key_rejects_invalid_run_dir() -> None:
    with pytest.raises(ValueError, match="run_dir_name"):
        current_view_object_key("INVALID NAME")


# ---- payload validation ----

def test_build_view_release_rejects_missing_run_dir() -> None:
    payload = _sample_payload()
    del payload["run_dir"]

    with pytest.raises(ValueError, match="run_dir"):
        build_view_release(payload)


def test_build_view_release_rejects_missing_run_json() -> None:
    payload = _sample_payload()
    del payload["run_json"]

    with pytest.raises(ValueError, match="run_json"):
        build_view_release(payload)


def test_build_view_release_rejects_missing_images() -> None:
    payload = _sample_payload()
    del payload["images"]

    with pytest.raises(ValueError, match="images"):
        build_view_release(payload)


def test_build_view_release_rejects_missing_x_columns() -> None:
    payload = _sample_payload()
    del payload["x_columns"]

    with pytest.raises(ValueError, match="x_columns"):
        build_view_release(payload)


def test_build_view_release_rejects_missing_y_indexes() -> None:
    payload = _sample_payload()
    del payload["y_indexes"]

    with pytest.raises(ValueError, match="y_indexes"):
        build_view_release(payload)


def test_build_view_release_rejects_missing_run_id_in_payload() -> None:
    payload = _sample_payload()
    del payload["run_id"]

    with pytest.raises(ValueError, match="run_id"):
        build_view_release(payload)


# ---- y_labels ----

def test_bootstrap_includes_y_labels() -> None:
    release = build_view_release(_sample_payload())

    for key in ("bootstrap_sfw", "bootstrap_nsfw"):
        y_labels = cast(list[str], release[key]["yLabels"])
        assert len(y_labels) == 1
        assert y_labels[0] == "cfg_7.0"


# ---- x_columns remap ----

def test_nsfw_column_remapped_in_sfw() -> None:
    release = build_view_release(_sample_payload())
    bootstrap = cast(dict[str, object], release["bootstrap_sfw"])

    x_columns = cast(list[dict[str, object]], bootstrap["x_columns"])
    assert len(x_columns) == 1
    assert x_columns[0]["type"] == "normal"


def test_all_columns_present_in_nsfw() -> None:
    release = build_view_release(_sample_payload())
    bootstrap = cast(dict[str, object], release["bootstrap_nsfw"])

    x_columns = cast(list[dict[str, object]], bootstrap["x_columns"])
    assert len(x_columns) == 2
    types = {cast(str, col["type"]) for col in x_columns}
    assert types == {"normal", "nsfw"}


# ---- current_manifest ----

def test_current_manifest_contains_urls() -> None:
    release = build_view_release(_sample_payload())

    current = cast(dict[str, object], release["current_manifest"])
    assert current["schema_version"] == VIEW_SCHEMA_VERSION
    assert current["run_dir"] == "chenkinnoob-xl-rf"
    assert "release_id" in current
    assert "bootstrap_sfw_key" in current
    assert "public_row_prefix" in current


# ---- prompt_rows ----

def test_prompt_rows_deduplication() -> None:
    payload = _sample_payload()
    # Both images share the same positive_prompt and prompt_hash,
    # so there should be only one prompt_row
    release = build_view_release(payload)

    prompt_rows = cast(list[dict[str, object]], release["prompt_rows"])
    assert len(prompt_rows) == 1
    assert prompt_rows[0]["positive_prompt"] == "a beautiful landscape"
    assert prompt_rows[0]["prompt_hash"] == "p1"
    assert prompt_rows[0]["run_dir"] == "chenkinnoob-xl-rf"


def test_prompt_rows_distinct_prompts() -> None:
    payload = _sample_payload()
    images = cast(list[dict[str, object]], payload["images"])
    images[1]["positive_prompt"] = "a different scene"
    images[1]["prompt_hash"] = "p2"

    release = build_view_release(payload)

    prompt_rows = cast(list[dict[str, object]], release["prompt_rows"])
    assert len(prompt_rows) == 2
