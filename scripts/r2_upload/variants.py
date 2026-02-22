# pyright: basic, reportMissingImports=false, reportMissingTypeStubs=false

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import cast

from blurhash import encode as blurhash_encode
from PIL import Image

from .encoding_params import avif_params, webp_params


def thumb_size(width: int, height: int) -> tuple[int, int]:
    if width < 1 or height < 1:
        raise ValueError("width and height must be positive")
    return (max(1, width // 2), max(1, height // 2))


def _fit_within(width: int, height: int, max_edge: int) -> tuple[int, int]:
    if width <= max_edge and height <= max_edge:
        return (width, height)

    scale = min(max_edge / width, max_edge / height)
    resized_width = max(1, math.floor(width * scale))
    resized_height = max(1, math.floor(height * scale))
    return (resized_width, resized_height)


def _coerce_upload_mode(image: Image.Image) -> Image.Image:
    if "A" in image.getbands():
        return image.convert("RGBA")
    return image.convert("RGB")


def _semantic_rgb_for_hash(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    composited = Image.alpha_composite(background, rgba)
    return composited.convert("RGB")


def _encode_to_bytes(
    image: Image.Image, *, image_format: str, params: dict[str, object]
) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=image_format, **params)
    return buffer.getvalue()


def _compute_blurhash_from_thumb(thumb_image: Image.Image) -> tuple[str, int, int]:
    semantic_rgb = _semantic_rgb_for_hash(thumb_image)
    target_size = _fit_within(semantic_rgb.width, semantic_rgb.height, max_edge=100)

    if semantic_rgb.size != target_size:
        semantic_rgb = cast(
            Image.Image,
            semantic_rgb.resize(target_size, Image.Resampling.LANCZOS),
        )

    rows: list[list[tuple[int, int, int]]] = []
    for y in range(semantic_rgb.height):
        row: list[tuple[int, int, int]] = []
        for x in range(semantic_rgb.width):
            r, g, b = cast(tuple[int, int, int], semantic_rgb.getpixel((x, y)))
            row.append((int(r), int(g), int(b)))
        rows.append(row)
    return (blurhash_encode(rows), semantic_rgb.width, semantic_rgb.height)


def inspect_image_metadata(image_path: Path) -> dict[str, object]:
    with Image.open(image_path) as opened_image:
        _ = opened_image.load()
        source = _coerce_upload_mode(opened_image)

    display_width = source.width
    display_height = source.height
    thumb = cast(
        Image.Image,
        source.resize(
            thumb_size(source.width, source.height),
            Image.Resampling.LANCZOS,
        ),
    )
    blurhash_value, _, _ = _compute_blurhash_from_thumb(thumb)
    return {
        "display_width": display_width,
        "display_height": display_height,
        "thumb_width": thumb.width,
        "thumb_height": thumb.height,
        "blurhash": blurhash_value,
    }


def plan_image_variants(image_path: Path) -> list[dict[str, object]]:
    with Image.open(image_path) as opened_image:
        _ = opened_image.load()
        source = _coerce_upload_mode(opened_image)

    display = source
    thumb = cast(
        Image.Image,
        source.resize(
            thumb_size(source.width, source.height),
            Image.Resampling.LANCZOS,
        ),
    )

    display_webp = _encode_to_bytes(
        display,
        image_format="WEBP",
        params=webp_params("display"),
    )
    display_avif = _encode_to_bytes(
        display,
        image_format="AVIF",
        params=avif_params("display"),
    )
    thumb_webp = _encode_to_bytes(
        thumb,
        image_format="WEBP",
        params=webp_params("thumb"),
    )
    thumb_avif = _encode_to_bytes(
        thumb,
        image_format="AVIF",
        params=avif_params("thumb"),
    )
    blurhash_value, blurhash_width, blurhash_height = _compute_blurhash_from_thumb(
        thumb
    )

    return [
        {
            "kind": "image",
            "level": "L1",
            "variant": "display_webp",
            "format": "WEBP",
            "width": display.width,
            "height": display.height,
            "bytes": display_webp,
        },
        {
            "kind": "image",
            "level": "L1",
            "variant": "display_avif",
            "format": "AVIF",
            "width": display.width,
            "height": display.height,
            "bytes": display_avif,
        },
        {
            "kind": "image",
            "level": "L2",
            "variant": "thumb_webp",
            "format": "WEBP",
            "width": thumb.width,
            "height": thumb.height,
            "bytes": thumb_webp,
        },
        {
            "kind": "image",
            "level": "L2",
            "variant": "thumb_avif",
            "format": "AVIF",
            "width": thumb.width,
            "height": thumb.height,
            "bytes": thumb_avif,
        },
        {
            "kind": "blurhash",
            "from_level": "L2",
            "variant": "thumb_blurhash",
            "value": blurhash_value,
            "hash_width": blurhash_width,
            "hash_height": blurhash_height,
        },
    ]
