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
    SCHEMA_VERSION,
    build_public_manifest,
    build_run_manifest,
    manifest_object_key,
)


def _sample_payload() -> dict[str, object]:
    return {
        "run_dir": "chenkinnoob-xl-rf",
        "images": [
            {
                "x_index": 0,
                "y_index": 0,
                "batch_index": 0,
                "category": "normal",
                "variants": [
                    {
                        "variant": "display_webp",
                        "bucket": "public",
                        "r2_key": "runs/public/normal-display.webp",
                        "content_type": "image/webp",
                        "byte_size": 123,
                    },
                    {
                        "variant": "original_png",
                        "bucket": "private",
                        "r2_key": "runs/private/normal-original.png",
                        "content_type": "image/png",
                        "byte_size": 456,
                    },
                ],
            },
            {
                "x_index": 1,
                "y_index": 0,
                "batch_index": 0,
                "category": "nsfw",
                "variants": [
                    {
                        "variant": "display_webp",
                        "bucket": "private",
                        "r2_key": "runs/private/nsfw-display.webp",
                        "content_type": "image/webp",
                        "byte_size": 222,
                    }
                ],
            },
        ],
    }


def test_build_run_manifest_includes_schema_version_and_isolation() -> None:
    payload = _sample_payload()

    manifest = build_run_manifest(payload)

    assert manifest["schema_version"] == SCHEMA_VERSION
    assert "schema_version" not in payload

    images = cast(list[dict[str, object]], manifest["images"])
    payload_images = cast(list[dict[str, object]], payload["images"])
    images[0]["category"] = "advance"
    assert payload_images[0]["category"] == "normal"


def test_build_public_manifest_redacts_private_content_and_keys() -> None:
    private_manifest = build_run_manifest(_sample_payload())

    public_manifest = build_public_manifest(private_manifest)

    images = cast(list[dict[str, object]], public_manifest["images"])
    assert len(images) == 1
    assert images[0]["category"] == "normal"

    variants = cast(list[dict[str, object]], images[0]["variants"])
    assert len(variants) == 1
    assert variants[0]["bucket"] == "public"
    assert variants[0]["r2_key"] == "runs/public/normal-display.webp"

    leaked_private_keys = [
        cast(str, variant["r2_key"])
        for image in images
        for variant in cast(list[dict[str, object]], image["variants"])
        if cast(str, variant["bucket"]) != "public"
        or "/private/" in cast(str, variant["r2_key"])
    ]
    assert leaked_private_keys == []

    private_images = cast(list[dict[str, object]], private_manifest["images"])
    assert len(private_images) == 2


def test_manifest_object_key_is_stable_and_contains_required_segments() -> None:
    manifest = build_run_manifest(_sample_payload())

    key1 = manifest_object_key("chenkinnoob-xl-rf", manifest, visibility="private")
    key2 = manifest_object_key("chenkinnoob-xl-rf", manifest, visibility="private")

    assert key1 == key2
    assert key1.startswith("manifests/private/runs/chenkinnoob-xl-rf/schema/1/")
    assert key1.endswith(".json")

    digest = key1.removesuffix(".json").split("/")[-1]
    assert len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)


def test_manifest_object_key_changes_with_schema_or_content() -> None:
    manifest = build_run_manifest(_sample_payload())

    base_key = manifest_object_key("chenkinnoob-xl-rf", manifest, visibility="public")

    schema_changed = copy.deepcopy(manifest)
    schema_changed["schema_version"] = 2
    schema_key = manifest_object_key(
        "chenkinnoob-xl-rf",
        schema_changed,
        visibility="public",
    )

    content_changed = copy.deepcopy(manifest)
    images = cast(list[dict[str, object]], content_changed["images"])
    images[0]["x_index"] = 999
    content_key = manifest_object_key(
        "chenkinnoob-xl-rf",
        content_changed,
        visibility="public",
    )

    assert base_key != schema_key
    assert "/schema/2/" in schema_key
    assert base_key != content_key


def test_manifest_object_key_rejects_invalid_inputs() -> None:
    manifest = build_run_manifest(_sample_payload())

    with pytest.raises(ValueError, match="run_dir_name"):
        manifest_object_key("NAI_4_FULL", manifest, visibility="public")

    with pytest.raises(ValueError, match="visibility"):
        manifest_object_key(
            "chenkinnoob-xl-rf",
            manifest,
            visibility=cast(Literal["public", "private"], "internal"),
        )
