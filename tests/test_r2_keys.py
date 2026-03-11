# pyright: basic, reportMissingImports=false

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.r2_keys import (
    bucket_for,
    cache_control_for,
    content_type_for,
    object_key,
)


ALL_VARIANTS = [
    "original_png",
    "display_webp",
    "display_avif",
    "thumb_webp",
    "thumb_avif",
]


def test_r2_key_is_deterministic_for_same_inputs() -> None:
    run_dir_name = "chenkinnoob-xl-rf"
    image_sha256 = "a" * 64

    key_1 = object_key(run_dir_name, image_sha256, "display_webp")
    key_2 = object_key(run_dir_name, image_sha256, "display_webp")

    assert key_1 == key_2


def test_r2_key_changes_when_variant_changes() -> None:
    run_dir_name = "chenkinnoob-xl-rf"
    image_sha256 = "b" * 64

    key_display = object_key(run_dir_name, image_sha256, "display_webp")
    key_thumb = object_key(run_dir_name, image_sha256, "thumb_webp")

    assert key_display != key_thumb


def test_r2_key_changes_when_sha_changes() -> None:
    run_dir_name = "chenkinnoob-xl-rf"

    key_1 = object_key(run_dir_name, "c" * 64, "display_avif")
    key_2 = object_key(run_dir_name, "d" * 64, "display_avif")

    assert key_1 != key_2


def test_r2_key_uses_expected_immutable_layout() -> None:
    run_dir_name = "chenkinnoob-xl-rf"
    image_sha256 = "0f" * 32

    key = object_key(run_dir_name, image_sha256, "thumb_avif")

    assert key == (
        "runs/chenkinnoob-xl-rf/"
        "sha256/0f/"
        "0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f/"
        "thumb_avif.avif"
    )


def test_r2_key_does_not_embed_absolute_local_paths() -> None:
    key = object_key("chenkinnoob-xl-rf", "e" * 64, "original_png")

    assert "/home/" not in key
    assert "C:\\" not in key


def test_r2_key_normalizes_sha256_to_lowercase() -> None:
    upper_sha256 = "AB" * 32
    key = object_key("chenkinnoob-xl-rf", upper_sha256, "display_webp")

    assert "/abababab" in key
    assert upper_sha256.lower() in key


def test_r2_key_rejects_invalid_run_dir_name() -> None:
    with pytest.raises(ValueError, match="run_dir_name"):
        object_key("NAI_4_FULL", "a" * 64, "display_webp")


def test_r2_key_rejects_invalid_sha256() -> None:
    with pytest.raises(ValueError, match="image_sha256"):
        object_key("chenkinnoob-xl-rf", "short", "display_webp")


def test_r2_key_rejects_unknown_variant() -> None:
    with pytest.raises(ValueError, match="variant"):
        object_key("chenkinnoob-xl-rf", "a" * 64, "raw_jpeg")


@pytest.mark.parametrize(
    "variant", ["display_webp", "display_avif", "thumb_webp", "thumb_avif"]
)
def test_r2_key_bucket_mapping_normal_public_for_display_and_thumb(
    variant: str,
) -> None:
    assert bucket_for("normal", variant) == "public"


def test_r2_key_bucket_mapping_normal_original_is_private() -> None:
    assert bucket_for("normal", "original_png") == "private"


@pytest.mark.parametrize("category", ["advance", "nsfw"])
@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_r2_key_bucket_mapping_advance_and_nsfw_always_private(
    category: str, variant: str
) -> None:
    assert bucket_for(category, variant) == "private"


def test_r2_key_bucket_mapping_rejects_unknown_category() -> None:
    with pytest.raises(ValueError, match="category"):
        bucket_for("unknown", "display_webp")


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        ("original_png", "image/png"),
        ("display_webp", "image/webp"),
        ("display_avif", "image/avif"),
        ("thumb_webp", "image/webp"),
        ("thumb_avif", "image/avif"),
    ],
)
def test_r2_key_content_type_mapping(variant: str, expected: str) -> None:
    assert content_type_for(variant) == expected


def test_r2_key_content_type_rejects_unknown_variant() -> None:
    with pytest.raises(ValueError, match="variant"):
        content_type_for("jpeg")


def test_r2_key_cache_control_for_public_bucket() -> None:
    assert cache_control_for("public") == "public, max-age=31536000, immutable"


def test_r2_key_cache_control_for_private_bucket() -> None:
    assert cache_control_for("private") == "private, max-age=0, no-cache"


def test_r2_key_cache_control_rejects_unknown_bucket() -> None:
    with pytest.raises(ValueError, match="bucket"):
        cache_control_for("internal")
