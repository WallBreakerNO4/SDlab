# pyright: basic, reportMissingImports=false

from __future__ import annotations

import io
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.encoding_params import EncodingKind, avif_params, webp_params

_KINDS: tuple[EncodingKind, EncodingKind] = ("display", "thumb")


def test_webp_params_use_required_quality_and_method() -> None:
    assert webp_params("display") == {"quality": 93, "method": 6}
    assert webp_params("thumb") == {"quality": 82, "method": 6}


def test_avif_params_keep_display_higher_quality_than_thumb() -> None:
    display = avif_params("display")
    thumb = avif_params("thumb")

    assert cast(int, display["quality"]) > cast(int, thumb["quality"])
    assert cast(int, display["speed"]) < cast(int, thumb["speed"])
    assert display["subsampling"] == "4:2:0"
    assert thumb["subsampling"] == "4:2:0"


def test_encoding_params_return_defensive_copies() -> None:
    params = webp_params("display")
    params["quality"] = 1

    assert webp_params("display") == {"quality": 93, "method": 6}


@pytest.mark.parametrize("kind", _KINDS)
def test_avif_params_can_encode_and_reopen_image(kind: EncodingKind) -> None:
    image = Image.new("RGB", (12, 12), (24, 48, 72))
    buffer = io.BytesIO()

    image.save(buffer, format="AVIF", **avif_params(kind))
    encoded_bytes = buffer.getvalue()
    assert len(encoded_bytes) > 0

    buffer.seek(0)
    with Image.open(buffer) as decoded:
        decoded.load()
        assert decoded.format == "AVIF"
        assert decoded.size == (12, 12)


@pytest.mark.parametrize(
    "getter",
    [
        cast(Callable[[str], dict[str, object]], webp_params),
        cast(Callable[[str], dict[str, object]], avif_params),
    ],
)
def test_encoding_params_reject_unknown_kind(
    getter: Callable[[str], dict[str, object]],
) -> None:
    with pytest.raises(ValueError, match="kind"):
        getter("raw")
