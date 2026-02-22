# pyright: basic, reportMissingImports=false

from __future__ import annotations

"""Central encoder params for R2 image variants.

WebP:
- display -> quality=93, method=4
- thumb -> quality=82, method=0

AVIF uses Pillow save args (quality/speed/subsampling), not CRF.
Chosen values keep "display higher quality than thumb":
- display -> quality=72, speed=8, subsampling="4:2:0"
- thumb -> quality=58, speed=9, subsampling="4:2:0"
"""

from typing import Final, Literal, cast

import pillow_avif

_ = pillow_avif

EncodingKind = Literal["display", "thumb"]

_WEBP_BY_KIND: Final[dict[EncodingKind, dict[str, object]]] = {
    "display": {"quality": 93, "method": 4},
    "thumb": {"quality": 82, "method": 0},
}

_AVIF_BY_KIND: Final[dict[EncodingKind, dict[str, object]]] = {
    "display": {"quality": 72, "speed": 8, "subsampling": "4:2:0"},
    "thumb": {"quality": 58, "speed": 9, "subsampling": "4:2:0"},
}


def _normalize_kind(kind: str) -> EncodingKind:
    if kind not in _WEBP_BY_KIND:
        raise ValueError(f"unsupported kind: {kind}")
    return cast(EncodingKind, kind)


def webp_params(kind: Literal["display", "thumb"]) -> dict[str, object]:
    normalized = _normalize_kind(kind)
    return dict(_WEBP_BY_KIND[normalized])


def avif_params(kind: Literal["display", "thumb"]) -> dict[str, object]:
    normalized = _normalize_kind(kind)
    return dict(_AVIF_BY_KIND[normalized])
