# pyright: basic, reportMissingImports=false

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.path_safety import (
    PathResolutionError,
    extract_local_image_path,
    extract_local_image_paths,
    is_path_safe_for_run_dir,
    normalize_run_dir,
    resolve_image_path,
    resolve_metadata_image_paths,
)


def test_normalize_run_dir_accepts_absolute_existing_dir(tmp_path: Path) -> None:
    """验证绝对路径的 run_dir 被接受并规范化"""
    run_dir = tmp_path / "run-test"
    run_dir.mkdir()

    normalized = normalize_run_dir(run_dir.resolve())
    assert normalized == run_dir.resolve()


def test_normalize_run_dir_accepts_relative_existing_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验证相对路径的 run_dir 被接受并解析为绝对路径"""
    run_dir = tmp_path / "run-test"
    run_dir.mkdir()

    monkeypatch.chdir(tmp_path)

    relative = Path("run-test")
    normalized = normalize_run_dir(relative)
    assert normalized == run_dir.resolve()
    assert normalized.is_absolute()


def test_normalize_run_dir_rejects_nonexistent_path() -> None:
    """不存在的路径应被拒绝"""
    with pytest.raises(PathResolutionError, match="run_dir 不存在"):
        normalize_run_dir(Path("/nonexistent/path"))


def test_normalize_run_dir_rejects_file_not_dir(tmp_path: Path) -> None:
    """文件而非目录应被拒绝"""
    file_path = tmp_path / "not-a-dir.txt"
    file_path.write_text("content")

    with pytest.raises(PathResolutionError, match="run_dir 不是目录"):
        normalize_run_dir(file_path.resolve())


def test_resolve_image_path_validates_path_under_images_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """正确的相对路径应被解析为绝对路径（支持相对和绝对 run_dir）"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    images_dir = run_dir / "images"
    images_dir.mkdir()
    image_file = images_dir / "x0-y0.png"
    image_file.write_bytes(b"png")

    resolved = resolve_image_path(run_dir.resolve(), "images/x0-y0.png")
    assert resolved == image_file.resolve()

    monkeypatch.chdir(tmp_path)
    resolved_from_relative = resolve_image_path(Path("run-dir"), "images/x0-y0.png")
    assert resolved_from_relative == image_file.resolve()


def test_resolve_image_path_rejects_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """以 / 开头的相对路径应被拒绝"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()

    with pytest.raises(PathResolutionError, match="相对路径不能以 / 或 \\\\ 开头"):
        resolve_image_path(run_dir.resolve(), "/etc/passwd")

    monkeypatch.chdir(tmp_path)
    with pytest.raises(PathResolutionError, match="相对路径不能以 / 或 \\\\ 开头"):
        resolve_image_path(Path("run-dir"), "/etc/passwd")


def test_resolve_image_path_rejects_windows_style_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows 风格绝对路径应被拒绝"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()

    with pytest.raises(PathResolutionError, match="相对路径不能以 / 或 \\\\ 开头"):
        resolve_image_path(run_dir.resolve(), "\\Windows\\System32")

    monkeypatch.chdir(tmp_path)
    with pytest.raises(PathResolutionError, match="相对路径不能以 / 或 \\\\ 开头"):
        resolve_image_path(Path("run-dir"), "\\Windows\\System32")


def test_resolve_image_path_rejects_path_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """路径遍历攻击（..）应被拒绝"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    (run_dir / "sensitive.txt").write_text("secret")

    with pytest.raises(PathResolutionError, match="不在允许的目录"):
        resolve_image_path(run_dir.resolve(), "images/../../../sensitive.txt")

    monkeypatch.chdir(tmp_path)
    with pytest.raises(PathResolutionError, match="不在允许的目录"):
        resolve_image_path(Path("run-dir"), "images/../../../sensitive.txt")


def test_resolve_image_path_rejects_path_outside_images_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """不在 images 目录下的路径应被拒绝"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    (run_dir / "other.txt").write_text("content")

    (tmp_path / "outside.txt").write_text("content")

    with pytest.raises(PathResolutionError, match="不在允许的目录"):
        resolve_image_path(run_dir.resolve(), "other.txt")

    monkeypatch.chdir(tmp_path)
    with pytest.raises(PathResolutionError, match="不在允许的目录"):
        resolve_image_path(Path("run-dir"), "other.txt")


def test_resolve_image_path_handles_symlink_inside_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """指向 images 内部的符号链接应被正确解析并验证"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    images_dir = run_dir / "images"
    images_dir.mkdir()

    image_file = images_dir / "real.png"
    image_file.write_bytes(b"png")

    symlink = images_dir / "link.png"
    symlink.symlink_to(image_file)

    resolved = resolve_image_path(run_dir.resolve(), "images/link.png")
    assert resolved.exists()

    monkeypatch.chdir(tmp_path)
    resolved_from_relative = resolve_image_path(Path("run-dir"), "images/link.png")
    assert resolved_from_relative.exists()


def test_resolve_image_path_rejects_symlink_outside_images(tmp_path: Path) -> None:
    """指向外部的符号链接应被拒绝"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    images_dir = run_dir / "images"
    images_dir.mkdir()

    outside_file = tmp_path / "outside.png"
    outside_file.write_bytes(b"png")

    symlink = images_dir / "link.png"
    symlink.symlink_to(outside_file)

    with pytest.raises(PathResolutionError, match="不在允许的目录"):
        resolve_image_path(run_dir.resolve(), "images/link.png")


def test_extract_local_image_path_returns_valid_string() -> None:
    """提取有效的 local_image_path"""
    record = {"local_image_path": "images/x0-y0.png"}
    assert extract_local_image_path(record) == "images/x0-y0.png"


def test_extract_local_image_path_strips_whitespace() -> None:
    """应去除路径前后空格"""
    record = {"local_image_path": "  images/x0-y0.png  "}
    assert extract_local_image_path(record) == "images/x0-y0.png"


def test_extract_local_image_path_returns_none_if_missing() -> None:
    """缺少字段时返回 None"""
    record: dict = {}
    assert extract_local_image_path(record) is None


def test_extract_local_image_path_returns_none_if_none_value() -> None:
    """值为 None 时返回 None"""
    record = {"local_image_path": None}
    assert extract_local_image_path(record) is None


def test_extract_local_image_path_returns_none_if_empty_string() -> None:
    """空字符串应返回 None"""
    record = {"local_image_path": ""}
    assert extract_local_image_path(record) is None


def test_extract_local_image_path_returns_none_if_whitespace_only() -> None:
    """仅包含空格的字符串应返回 None"""
    record = {"local_image_path": "   "}
    assert extract_local_image_path(record) is None


def test_extract_local_image_path_returns_none_if_not_string() -> None:
    """非字符串类型应返回 None"""
    record = {"local_image_path": 123}
    assert extract_local_image_path(record) is None


def test_extract_local_image_paths_returns_valid_list() -> None:
    """提取有效的 local_image_paths 列表"""
    record = {"local_image_paths": ["images/x0-y0.png", "images/x1-y1.png"]}
    assert extract_local_image_paths(record) == ["images/x0-y0.png", "images/x1-y1.png"]


def test_extract_local_image_paths_filters_empty_strings() -> None:
    """应过滤空字符串"""
    record = {"local_image_paths": ["images/x0-y0.png", "", "images/x1-y1.png"]}
    assert extract_local_image_paths(record) == ["images/x0-y0.png", "images/x1-y1.png"]


def test_extract_local_image_paths_strips_whitespace() -> None:
    """应去除每个路径的前后空格"""
    record = {"local_image_paths": ["  images/x0-y0.png  ", "  images/x1-y1.png  "]}
    assert extract_local_image_paths(record) == ["images/x0-y0.png", "images/x1-y1.png"]


def test_extract_local_image_paths_returns_none_if_missing() -> None:
    """缺少字段时返回 None"""
    record: dict = {}
    assert extract_local_image_paths(record) is None


def test_extract_local_image_paths_returns_none_if_not_list() -> None:
    """非列表类型应返回 None"""
    record = {"local_image_paths": "not a list"}
    assert extract_local_image_paths(record) is None


def test_extract_local_image_paths_returns_none_if_empty_list() -> None:
    """空列表应返回 None"""
    record = {"local_image_paths": []}
    assert extract_local_image_paths(record) is None


def test_extract_local_image_paths_returns_none_if_contains_non_string() -> None:
    """包含非字符串元素时应返回 None"""
    record = {"local_image_paths": ["images/x0-y0.png", 123]}
    assert extract_local_image_paths(record) is None


def test_resolve_metadata_image_paths_uses_local_image_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """优先使用 local_image_paths（支持相对和绝对 run_dir）"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    images_dir = run_dir / "images"
    images_dir.mkdir()
    (images_dir / "x0-y0.png").write_bytes(b"png")
    (images_dir / "x0-y0-1.png").write_bytes(b"png")

    record = {
        "local_image_paths": ["images/x0-y0.png", "images/x0-y0-1.png"],
        "local_image_path": "images/x0-y0.png",
    }

    paths = resolve_metadata_image_paths(run_dir.resolve(), record)
    assert len(paths) == 2
    assert paths[0].name == "x0-y0.png"
    assert paths[1].name == "x0-y0-1.png"

    monkeypatch.chdir(tmp_path)
    paths_from_relative = resolve_metadata_image_paths(Path("run-dir"), record)
    assert len(paths_from_relative) == 2
    assert paths_from_relative[0].name == "x0-y0.png"
    assert paths_from_relative[1].name == "x0-y0-1.png"


def test_resolve_metadata_image_paths_falls_back_to_local_image_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """local_image_paths 不存在时回退到 local_image_path"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    images_dir = run_dir / "images"
    images_dir.mkdir()
    (images_dir / "x0-y0.png").write_bytes(b"png")

    record = {"local_image_path": "images/x0-y0.png"}

    paths = resolve_metadata_image_paths(run_dir.resolve(), record)
    assert len(paths) == 1
    assert paths[0].name == "x0-y0.png"

    monkeypatch.chdir(tmp_path)
    paths_from_relative = resolve_metadata_image_paths(Path("run-dir"), record)
    assert len(paths_from_relative) == 1
    assert paths_from_relative[0].name == "x0-y0.png"


def test_resolve_metadata_image_paths_returns_empty_list_if_none_provided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """两者都不存在时返回空列表"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    images_dir = run_dir / "images"
    images_dir.mkdir()

    record: dict = {}

    paths = resolve_metadata_image_paths(run_dir.resolve(), record)
    assert paths == []

    monkeypatch.chdir(tmp_path)
    paths_from_relative = resolve_metadata_image_paths(Path("run-dir"), record)
    assert paths_from_relative == []


def test_resolve_metadata_image_paths_validates_all_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """所有路径都应经过安全验证"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    images_dir = run_dir / "images"
    images_dir.mkdir()
    (images_dir / "x0-y0.png").write_bytes(b"png")

    record = {"local_image_paths": ["images/x0-y0.png", "/etc/passwd"]}

    with pytest.raises(PathResolutionError):
        resolve_metadata_image_paths(run_dir.resolve(), record)

    monkeypatch.chdir(tmp_path)
    with pytest.raises(PathResolutionError):
        resolve_metadata_image_paths(Path("run-dir"), record)


def test_resolve_metadata_image_paths_validates_run_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_dir 本身应被验证"""
    record = {"local_image_path": "images/x0-y0.png"}

    with pytest.raises(PathResolutionError, match="run_dir 不存在"):
        resolve_metadata_image_paths(Path("/nonexistent"), record)

    monkeypatch.chdir(tmp_path)
    run_not_exist = tmp_path / "run-not-exist"
    with pytest.raises(PathResolutionError, match="run_dir 不存在"):
        resolve_metadata_image_paths(run_not_exist, record)


def test_is_path_safe_for_run_dir_returns_true_for_valid_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """有效路径应返回 True"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    images_dir = run_dir / "images"
    images_dir.mkdir()
    image_file = images_dir / "x0-y0.png"
    image_file.write_bytes(b"png")

    assert is_path_safe_for_run_dir(run_dir.resolve(), image_file.resolve())

    monkeypatch.chdir(tmp_path)
    assert is_path_safe_for_run_dir(Path("run-dir"), image_file.resolve())


def test_is_path_safe_for_run_dir_returns_false_for_outside_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """外部路径应返回 False"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("content")

    assert not is_path_safe_for_run_dir(run_dir.resolve(), outside_file.resolve())

    monkeypatch.chdir(tmp_path)
    assert not is_path_safe_for_run_dir(Path("run-dir"), outside_file.resolve())


def test_is_path_safe_for_run_dir_returns_false_for_path_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """路径遍历应返回 False"""
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    sensitive_file = tmp_path / "sensitive.txt"
    sensitive_file.write_text("secret")

    assert not is_path_safe_for_run_dir(run_dir.resolve(), sensitive_file.resolve())

    monkeypatch.chdir(tmp_path)
    assert not is_path_safe_for_run_dir(Path("run-dir"), sensitive_file.resolve())
