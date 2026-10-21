# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from scripts.run_naming import RUN_KEY_RE

from .run_assets import RunAssetsScan

Category = Literal["normal", "advance", "nsfw"]
BucketScope = Literal["public", "private"]
EvaluationStatus = Literal["in_progress", "complete"]

EVALUATION_STATUS_IN_PROGRESS: EvaluationStatus = "in_progress"
EVALUATION_STATUS_COMPLETE: EvaluationStatus = "complete"
EVALUATION_STATUSES: frozenset[EvaluationStatus] = frozenset(
    {EVALUATION_STATUS_IN_PROGRESS, EVALUATION_STATUS_COMPLETE}
)

_RUN_DIR_NAME_RE = RUN_KEY_RE
_CATEGORY_CHOICES: tuple[Category, Category, Category] = (
    "normal",
    "advance",
    "nsfw",
)
_IMAGE_VARIANTS = {
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
    artifact_uploads: list[PlannedUpload]
    manifest_uploads: list[PlannedUpload]
    asset_scan: RunAssetsScan
    snapshot_status: EvaluationStatus
    generated_cells: int
    planned_cells: int


def snapshot_stats_report(
    plan: RunPlan,
    *,
    status: EvaluationStatus | None = None,
) -> dict[str, object]:
    """dry-run 与执行报告共享的快照状态摘要（status 可传生效状态）。"""
    return {
        "run_dir": plan.run_dir_name,
        "status": status if status is not None else plan.snapshot_status,
        "generated_cells": plan.generated_cells,
        "planned_cells": plan.planned_cells,
    }


@dataclass(frozen=True)
class PlannedImageTask:
    index: int
    image_path: Path
    metadata_record: dict[str, object]
    category: Category
    batch_index: int
