# pyright: basic

from __future__ import annotations

from pathlib import Path


class PathResolutionError(Exception):
    """路径解析失败或路径不安全"""

    pass


def normalize_run_dir(run_dir: Path) -> Path:
    """
    验证并规范化 run_dir 为绝对路径

    Args:
        run_dir: 运行目录路径（可以是相对或绝对路径）

    Returns:
        规范化的绝对路径

    Raises:
        PathResolutionError: 如果 run_dir 不存在或不是目录
    """
    if not run_dir.exists():
        raise PathResolutionError(f"run_dir 不存在: {run_dir}")

    if not run_dir.is_dir():
        raise PathResolutionError(f"run_dir 不是目录: {run_dir}")

    return run_dir.resolve()


def resolve_image_path(run_dir: Path, relative_path: str) -> Path:
    """
    从相对路径安全解析图片的绝对路径

    Args:
        run_dir: 运行目录（可以是相对或绝对路径）
        relative_path: 相对路径（如 "images/x0-y0.png"）

    Returns:
        图片的绝对路径（已验证在 run_dir/images/ 下）

    Raises:
        PathResolutionError: 如果路径不安全或超出允许范围
    """
    normalized_run_dir = normalize_run_dir(run_dir)

    # 确保相对路径不以 / 开头（避免被视为绝对路径）
    if relative_path.startswith("/") or relative_path.startswith("\\"):
        raise PathResolutionError(f"相对路径不能以 / 或 \\ 开头: {relative_path}")

    # 解析相对路径
    try:
        candidate = normalized_run_dir / relative_path
    except Exception as exc:
        raise PathResolutionError(f"无法解析路径 {relative_path}: {exc}") from exc

    # 规范化路径，解析 .. 和符号链接
    try:
        resolved = candidate.resolve(strict=False)
    except Exception as exc:
        raise PathResolutionError(f"无法规范化路径 {candidate}: {exc}") from exc

    # 验证路径在 run_dir/images/ 下
    images_dir = (normalized_run_dir / "images").resolve(strict=False)

    # 检查 resolved 是否是 images_dir 的子路径
    try:
        resolved.relative_to(images_dir)
    except ValueError as exc:
        raise PathResolutionError(
            f"路径 {relative_path} 解析到 {resolved}，不在允许的目录 {images_dir} 下"
        ) from exc

    return resolved


def extract_local_image_path(metadata_record: dict) -> str | None:
    """
    从 metadata 记录中提取 local_image_path

    Args:
        metadata_record: metadata.jsonl 中的单条记录

    Returns:
        提取到的相对路径字符串，如果不存在或无效则返回 None
    """
    value = metadata_record.get("local_image_path")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def extract_local_image_paths(metadata_record: dict) -> list[str] | None:
    """
    从 metadata 记录中提取 local_image_paths

    Args:
        metadata_record: metadata.jsonl 中的单条记录

    Returns:
        提取到的相对路径字符串列表，如果不存在或无效则返回 None
    """
    value = metadata_record.get("local_image_paths")
    if not isinstance(value, list) or not value:
        return None

    paths: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        stripped = item.strip()
        if not stripped:
            continue
        paths.append(stripped)

    return paths if paths else None


def resolve_metadata_image_paths(run_dir: Path, metadata_record: dict) -> list[Path]:
    """
    从 metadata 记录中安全解析所有图片的绝对路径

    优先使用 local_image_paths，如果不存在则回退到 local_image_path

    Args:
        run_dir: 运行目录（可以是相对或绝对路径）
        metadata_record: metadata.jsonl 中的单条记录

    Returns:
        图片绝对路径列表（已验证在 run_dir/images/ 下）

    Raises:
        PathResolutionError: 如果 run_dir 无效或路径解析失败
    """
    # 尝试从 local_image_paths 提取
    paths_from_list = extract_local_image_paths(metadata_record)
    if paths_from_list is not None:
        return [resolve_image_path(run_dir, p) for p in paths_from_list]

    # 回退到 local_image_path
    path_from_single = extract_local_image_path(metadata_record)
    if path_from_single is not None:
        return [resolve_image_path(run_dir, path_from_single)]

    # 两者都不存在，返回空列表
    return []


def is_path_safe_for_run_dir(run_dir: Path, absolute_path: Path) -> bool:
    """
    检查绝对路径是否在允许的 run_dir/images/ 范围内

    Args:
        run_dir: 运行目录（可以是相对或绝对路径）
        absolute_path: 要检查的绝对路径

    Returns:
        如果路径在允许范围内返回 True，否则返回 False
    """
    try:
        normalized_run_dir = normalize_run_dir(run_dir)
        relative_path = str(absolute_path.relative_to(normalized_run_dir))
        resolve_image_path(normalized_run_dir, relative_path)
        return True
    except Exception:
        return False
