# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Category = Literal["normal", "advance", "nsfw"]
BucketScope = Literal["public", "private"]

_RUN_DIR_NAME_RE = re.compile(r"^run-\d{8}T\d{6}Z$")
_CATEGORY_CHOICES: tuple[Category, Category, Category] = (
    "normal",
    "advance",
    "nsfw",
)
_IMAGE_VARIANTS = {
    "original_png",
    "display_webp",
    "display_avif",
    "thumb_webp",
    "thumb_avif",
}
_DERIVED_IMAGE_VARIANTS: tuple[str, str, str, str] = (
    "display_webp",
    "display_avif",
    "thumb_webp",
    "thumb_avif",
)

_EXIT_CODES_BY_CATEGORY: dict[str, int] = {
    "argument": 2,
    "config": 3,
    "auth": 4,
    "network": 5,
    "rate_limit": 6,
    "retry_exhausted": 7,
    "remote": 8,
    "unexpected": 9,
}


class UploadScriptError(RuntimeError):
    category: str

    def __init__(self, message: str, *, category: str) -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class PlannedUpload:
    variant: str
    bucket_scope: BucketScope
    key: str
    content_type: str
    cache_control: str
    byte_size: int
    body_bytes: bytes | None = None
    local_path: Path | None = None

    def to_safe_json(self) -> dict[str, object]:
        return {
            "variant": self.variant,
            "bucket_scope": self.bucket_scope,
            "key": self.key,
            "content_type": self.content_type,
            "cache_control": self.cache_control,
            "byte_size": self.byte_size,
            "source": "local_path" if self.local_path is not None else "body_bytes",
        }


@dataclass(frozen=True)
class RunPlan:
    run_dir: Path
    run_dir_name: str
    intermediate_dir: Path
    processed_images: int
    upload_index_payload: dict[str, object]
    image_uploads: list[PlannedUpload]
    manifest_uploads: list[PlannedUpload]


@dataclass(frozen=True)
class PlannedImageTask:
    index: int
    image_path: Path
    metadata_record: dict[str, object]
    category: Category
    batch_index: int
