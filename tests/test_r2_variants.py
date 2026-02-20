# pyright: basic, reportMissingImports=false

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import cast

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.variants import plan_image_variants, thumb_size


def _write_test_png(path: Path, *, size: tuple[int, int], mode: str = "RGBA") -> None:
    image = Image.new(mode, size)

    for y in range(size[1]):
        for x in range(size[0]):
            if mode == "RGBA":
                image.putpixel(
                    (x, y), (x * 17 % 256, y * 29 % 256, (x + y) * 11 % 256, 180)
                )
            else:
                image.putpixel((x, y), (x * 17 % 256, y * 29 % 256, (x + y) * 11 % 256))

    image.save(path, format="PNG")


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (8, 6, (4, 3)),
        (9, 7, (4, 3)),
        (1, 1, (1, 1)),
        (2, 1, (1, 1)),
    ],
)
def test_thumb_size_halves_with_floor_and_never_zero(
    width: int, height: int, expected: tuple[int, int]
) -> None:
    assert thumb_size(width, height) == expected


@pytest.mark.parametrize(("width", "height"), [(0, 1), (1, 0), (-1, 2), (2, -1)])
def test_thumb_size_rejects_non_positive_dims(width: int, height: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        thumb_size(width, height)


def test_plan_image_variants_generates_l1_l2_and_blurhash(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    _write_test_png(source_path, size=(9, 7), mode="RGBA")

    variants = plan_image_variants(source_path)

    assert len(variants) == 5

    image_variants = {
        str(item["variant"]): item for item in variants if item["kind"] == "image"
    }
    blurhash_variant = next(item for item in variants if item["kind"] == "blurhash")

    assert set(image_variants) == {
        "display_webp",
        "display_avif",
        "thumb_webp",
        "thumb_avif",
    }

    assert image_variants["display_webp"]["width"] == 9
    assert image_variants["display_webp"]["height"] == 7
    assert image_variants["display_avif"]["width"] == 9
    assert image_variants["display_avif"]["height"] == 7
    assert image_variants["thumb_webp"]["width"] == 4
    assert image_variants["thumb_webp"]["height"] == 3
    assert image_variants["thumb_avif"]["width"] == 4
    assert image_variants["thumb_avif"]["height"] == 3

    for variant_name, expected_format in [
        ("display_webp", "WEBP"),
        ("display_avif", "AVIF"),
        ("thumb_webp", "WEBP"),
        ("thumb_avif", "AVIF"),
    ]:
        payload = image_variants[variant_name]
        encoded = cast(bytes, payload["bytes"])
        assert len(encoded) > 0
        width = cast(int, payload["width"])
        height = cast(int, payload["height"])

        with Image.open(io.BytesIO(encoded)) as decoded:
            decoded.load()
            assert decoded.format == expected_format
            assert decoded.size == (width, height)

    assert blurhash_variant["variant"] == "thumb_blurhash"
    assert isinstance(blurhash_variant["value"], str)
    assert len(str(blurhash_variant["value"])) >= 6
    assert cast(int, blurhash_variant["hash_width"]) <= 100
    assert cast(int, blurhash_variant["hash_height"]) <= 100


def test_plan_image_variants_is_deterministic_for_same_input(tmp_path: Path) -> None:
    source_path = tmp_path / "deterministic.png"
    _write_test_png(source_path, size=(64, 48), mode="RGB")

    first = plan_image_variants(source_path)
    second = plan_image_variants(source_path)

    assert first == second


def test_blurhash_resizes_l2_to_max_100_edge(tmp_path: Path) -> None:
    source_path = tmp_path / "large.png"
    _write_test_png(source_path, size=(801, 607), mode="RGB")

    variants = plan_image_variants(source_path)
    blurhash_variant = next(item for item in variants if item["kind"] == "blurhash")

    hash_width = cast(int, blurhash_variant["hash_width"])
    hash_height = cast(int, blurhash_variant["hash_height"])

    assert (hash_width, hash_height) == (100, 75)
