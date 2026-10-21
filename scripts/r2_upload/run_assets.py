# pyright: basic, reportUnknownVariableType=false

"""发布时现场扫描 run 级静态资产（封面图 / 主页缩略图）。

识别规则与生图侧 `scripts/generation/runner_config.py:_load_assets` 保持一致，
两侧的接受 / 拒绝行为由 `tests/test_r2_upload_run_assets.py` 的契约测试对齐。
扫描目录由 run.json 的 `config_path` 定位（生成侧资产目录），不读取 run.json
中的 assets 快照。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from scripts.run_config_path import resolve_run_config_path

from .upload_io import _sha256_file

LOG = logging.getLogger(__name__)

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".avif"})
_COVER_STEM = "image"
_HOMEPAGE_DIR_NAME = "images"


@dataclass(frozen=True)
class RunAssetRef:
    path: Path
    repo_relative_path: str
    sha256: str

    def to_payload(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "repo_relative_path": self.repo_relative_path,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class RunAssetsScan:
    cover_image: RunAssetRef | None
    homepage_images: tuple[RunAssetRef, ...]

    def assets_payload(self) -> dict[str, object]:
        return {
            "cover_image": (
                self.cover_image.to_payload()
                if self.cover_image is not None
                else None
            ),
            "homepage_images": [
                asset.to_payload() for asset in self.homepage_images
            ],
        }

    def to_report(self) -> dict[str, object]:
        return {
            "cover_image": (
                self.cover_image.repo_relative_path
                if self.cover_image is not None
                else None
            ),
            "homepage_images": [
                asset.repo_relative_path for asset in self.homepage_images
            ],
        }


def asset_scan_report(
    run_dir_name: str, scan: RunAssetsScan
) -> dict[str, object]:
    return {"run_dir": run_dir_name, **scan.to_report()}


def _non_empty_str(value: object) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed:
            return trimmed
    return None


def _build_asset_ref(*, path: Path, repo_root: Path) -> RunAssetRef:
    resolved = path.resolve()
    return RunAssetRef(
        path=resolved,
        repo_relative_path=resolved.relative_to(repo_root).as_posix(),
        sha256=_sha256_file(resolved),
    )


def resolve_run_asset_dir(
    run_json: dict[str, object], *, repo_root: Path
) -> Path | None:
    resolved_root = repo_root.resolve()

    config_path = _non_empty_str(run_json.get("config_path"))
    if config_path is None:
        return None

    config_file = resolve_run_config_path(config_path, repo_root=resolved_root)
    if not config_file.is_relative_to(resolved_root):
        raise ValueError(f"run.json 中 config_path 越界: {config_path}")
    return config_file.parent


def scan_asset_directory(asset_dir: Path, *, repo_root: Path) -> RunAssetsScan:
    resolved_dir = asset_dir.resolve()
    resolved_root = repo_root.resolve()

    cover_image_candidates = sorted(
        path
        for path in resolved_dir.iterdir()
        if path.is_file()
        and path.stem == _COVER_STEM
        and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if len(cover_image_candidates) > 1:
        names = ", ".join(path.name for path in cover_image_candidates)
        raise ValueError(f"run 封面图存在多个 image.* 文件: {names}")

    cover_image = (
        _build_asset_ref(path=cover_image_candidates[0], repo_root=resolved_root)
        if cover_image_candidates
        else None
    )

    homepage_image_dir = resolved_dir / _HOMEPAGE_DIR_NAME
    homepage_images: list[RunAssetRef] = []
    if homepage_image_dir.exists():
        if not homepage_image_dir.is_dir():
            raise ValueError(f"run 主页缩略图目录不是文件夹: {homepage_image_dir}")
        for path in sorted(homepage_image_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            homepage_images.append(
                _build_asset_ref(path=path, repo_root=resolved_root)
            )

    return RunAssetsScan(
        cover_image=cover_image,
        homepage_images=tuple(homepage_images),
    )


def scan_run_assets(
    *,
    run_json: dict[str, object],
    repo_root: Path,
) -> RunAssetsScan:
    asset_dir = resolve_run_asset_dir(run_json, repo_root=repo_root)
    if asset_dir is None:
        return RunAssetsScan(cover_image=None, homepage_images=())
    if not asset_dir.is_dir():
        LOG.warning("run 资产目录不存在，按无资产处理: %s", asset_dir)
        return RunAssetsScan(cover_image=None, homepage_images=())
    return scan_asset_directory(asset_dir, repo_root=repo_root)
