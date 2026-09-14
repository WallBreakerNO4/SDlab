# pyright: basic, reportMissingImports=false

"""上传端资产扫描与生图侧识别规则的契约测试。

同一组夹具必须被两侧接受 / 拒绝一致，防止封面图与主页缩略图的识别规则漂移。
"""

from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generation.runner_config import (
    _IMAGE_EXTENSIONS as GENERATION_IMAGE_EXTENSIONS,
)
from scripts.generation.runner_config import _load_assets as load_generation_assets
from scripts.r2_upload.run_assets import (
    IMAGE_EXTENSIONS,
    RunAssetsScan,
    resolve_run_asset_dir,
    scan_asset_directory,
    scan_run_assets,
)


@dataclass(frozen=True)
class _Outcome:
    rejected: bool
    cover: tuple[str, str] | None
    homepage: tuple[tuple[str, str], ...]


def _generation_outcome(asset_dir: Path, *, repo_root: Path) -> _Outcome:
    try:
        assets = load_generation_assets(run_dir=asset_dir, repo_root=repo_root)
    except ValueError:
        return _Outcome(rejected=True, cover=None, homepage=())
    return _Outcome(
        rejected=False,
        cover=(
            (assets.cover_image.repo_relative_path, assets.cover_image.sha256)
            if assets.cover_image is not None
            else None
        ),
        homepage=tuple(
            (asset.repo_relative_path, asset.sha256)
            for asset in assets.homepage_images
        ),
    )


def _upload_outcome(asset_dir: Path, *, repo_root: Path) -> _Outcome:
    try:
        scan = scan_asset_directory(asset_dir, repo_root=repo_root)
    except ValueError:
        return _Outcome(rejected=True, cover=None, homepage=())
    return _Outcome(
        rejected=False,
        cover=(
            (scan.cover_image.repo_relative_path, scan.cover_image.sha256)
            if scan.cover_image is not None
            else None
        ),
        homepage=tuple(
            (asset.repo_relative_path, asset.sha256)
            for asset in scan.homepage_images
        ),
    )


def _materialize_asset_dir(
    repo_root: Path,
    *,
    dirs: tuple[str, ...],
    files: tuple[str, ...],
    case_name: str,
) -> Path:
    asset_dir = repo_root / "data/models/example"
    asset_dir.mkdir(parents=True, exist_ok=True)
    for relative_dir in dirs:
        (asset_dir / relative_dir).mkdir(parents=True, exist_ok=True)
    for relative_file in files:
        file_path = asset_dir / relative_file
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(f"{case_name}:{relative_file}".encode("utf-8"))
    return asset_dir


# (case, dirs, files, expected rejected, expected cover, expected homepage count)
ASSET_SCAN_CASES = [
    ("cover_jpg", (), ("image.jpg",), False, "image.jpg", 0),
    ("cover_jpeg", (), ("image.jpeg",), False, "image.jpeg", 0),
    ("cover_png", (), ("image.png",), False, "image.png", 0),
    ("cover_webp", (), ("image.webp",), False, "image.webp", 0),
    ("cover_avif", (), ("image.avif",), False, "image.avif", 0),
    ("cover_uppercase_extension", (), ("image.PNG",), False, "image.PNG", 0),
    ("cover_other_extension_ignored", (), ("image.txt",), False, None, 0),
    ("cover_composite_stem_ignored", (), ("image.backup.png",), False, None, 0),
    (
        "multiple_covers_rejected",
        (),
        ("image.jpg", "image.png"),
        True,
        None,
        0,
    ),
    (
        "multiple_covers_case_insensitive_rejected",
        (),
        ("image.jpg", "image.JPG"),
        True,
        None,
        0,
    ),
    ("no_assets", (), (), False, None, 0),
    (
        "cover_and_homepage",
        (),
        ("image.png", "images/a.png", "images/b.jpeg"),
        False,
        "image.png",
        2,
    ),
    ("homepage_only", (), ("images/a.png",), False, None, 1),
    (
        "homepage_sorted",
        (),
        ("images/b.png", "images/a.png", "images/c.webp"),
        False,
        None,
        3,
    ),
    (
        "homepage_ignores_non_images",
        (),
        ("images/a.png", "images/readme.txt", "images/notes.md"),
        False,
        None,
        1,
    ),
    (
        "homepage_ignores_subdir",
        ("images/sub",),
        ("images/a.png", "images/sub/b.png"),
        False,
        None,
        1,
    ),
    ("homepage_hidden_image", (), ("images/.hidden.png",), False, None, 1),
    ("homepage_dir_is_file_rejected", (), ("images",), True, None, 0),
    ("homepage_empty_dir", ("images",), (), False, None, 0),
    (
        "nested_image_only_counts_as_homepage",
        (),
        ("images/image.png",),
        False,
        None,
        1,
    ),
]


@pytest.mark.parametrize(
    (
        "case_name",
        "dirs",
        "files",
        "expected_rejected",
        "expected_cover",
        "expected_homepage_count",
    ),
    ASSET_SCAN_CASES,
)
def test_upload_scan_matches_generation_rule_on_shared_fixtures(
    tmp_path: Path,
    case_name: str,
    dirs: tuple[str, ...],
    files: tuple[str, ...],
    expected_rejected: bool,
    expected_cover: str | None,
    expected_homepage_count: int,
) -> None:
    asset_dir = _materialize_asset_dir(
        tmp_path,
        dirs=dirs,
        files=files,
        case_name=case_name,
    )

    upload_outcome = _upload_outcome(asset_dir, repo_root=tmp_path)
    generation_outcome = _generation_outcome(asset_dir, repo_root=tmp_path)

    assert upload_outcome.rejected is expected_rejected
    if expected_rejected:
        assert upload_outcome.cover is None
        assert upload_outcome.homepage == ()
    else:
        cover_path = (
            f"data/models/example/{expected_cover}"
            if expected_cover is not None
            else None
        )
        assert (upload_outcome.cover or (None,))[0] == cover_path
        assert len(upload_outcome.homepage) == expected_homepage_count

    assert upload_outcome == generation_outcome


def test_scan_homepage_order_is_sorted_by_path(tmp_path: Path) -> None:
    asset_dir = _materialize_asset_dir(
        tmp_path,
        dirs=(),
        files=("images/c.png", "images/a.png", "images/b.png"),
        case_name="homepage_order",
    )

    scan = scan_asset_directory(asset_dir, repo_root=tmp_path)

    assert [Path(ref.repo_relative_path).name for ref in scan.homepage_images] == [
        "a.png",
        "b.png",
        "c.png",
    ]


@pytest.mark.parametrize(
    "extension",
    sorted(GENERATION_IMAGE_EXTENSIONS | IMAGE_EXTENSIONS),
)
def test_upload_scan_matches_generation_extension_set(
    tmp_path: Path, extension: str
) -> None:
    """任一侧新增 / 移除图片扩展名都会因两侧结果不一致而失败。"""
    asset_dir = _materialize_asset_dir(
        tmp_path,
        dirs=(),
        files=(f"image{extension}", f"images/card{extension}"),
        case_name=f"extension{extension}",
    )

    upload_outcome = _upload_outcome(asset_dir, repo_root=tmp_path)
    generation_outcome = _generation_outcome(asset_dir, repo_root=tmp_path)

    assert upload_outcome == generation_outcome
    assert upload_outcome.rejected is False


def test_resolve_run_asset_dir_prefers_config_path_parent(tmp_path: Path) -> None:
    config_file = tmp_path / "data/models/example/config.yaml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("schema_version: image-run-config/v1\n", encoding="utf-8")

    resolved = resolve_run_asset_dir(
        {"config_path": "data/models/example/config.yaml"},
        repo_root=tmp_path,
    )

    assert resolved == config_file.parent


def test_resolve_run_asset_dir_ignores_snapshot_assets(tmp_path: Path) -> None:
    resolved = resolve_run_asset_dir(
        {
            "assets": {
                "cover_image": None,
                "homepage_images": [
                    {"repo_relative_path": "data/models/example/images/a.png"},
                ],
            }
        },
        repo_root=tmp_path,
    )

    assert resolved is None


def test_resolve_run_asset_dir_returns_none_without_any_hint() -> None:
    assert resolve_run_asset_dir({}, repo_root=Path.cwd()) is None


def test_resolve_run_asset_dir_rejects_path_outside_repo(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="越界"):
        _ = resolve_run_asset_dir(
            {"config_path": "../outside/config.yaml"},
            repo_root=tmp_path,
        )


def test_scan_run_assets_returns_empty_scan_when_asset_dir_missing(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    scan = scan_run_assets(
        run_json={"config_path": "data/models/missing/config.yaml"},
        repo_root=tmp_path,
    )

    assert isinstance(scan, RunAssetsScan)
    assert scan.cover_image is None
    assert scan.homepage_images == ()
    assert any("资产目录不存在" in record.message for record in caplog.records)
