from __future__ import annotations

from pathlib import Path


DATA_RUNS_DIR = Path("data/runs")
DEFAULT_RUN_CONFIG_NAME = "config.yaml"
_CONFIG_SUFFIXES = {".yaml", ".yml", ".json"}


def iter_run_config_files(data_runs_dir: Path = DATA_RUNS_DIR) -> list[Path]:
    if not data_runs_dir.exists():
        return []

    config_files: list[Path] = []
    for child in sorted(data_runs_dir.iterdir(), key=lambda path: path.as_posix()):
        if child.is_file() and child.suffix.lower() in _CONFIG_SUFFIXES:
            config_files.append(child)
            continue
        if not child.is_dir():
            continue

        config_file = child / DEFAULT_RUN_CONFIG_NAME
        if config_file.is_file():
            config_files.append(config_file)

    return config_files


def normalize_run_config_path(config_path: str) -> str:
    normalized = Path(config_path.strip()).as_posix()
    candidate = Path(normalized)
    if candidate.name == DEFAULT_RUN_CONFIG_NAME:
        return normalized

    if len(candidate.parts) != 3:
        return normalized

    data_dir, runs_dir, filename = candidate.parts
    if data_dir != "data" or runs_dir != "runs":
        return normalized

    if candidate.suffix.lower() not in _CONFIG_SUFFIXES:
        return normalized

    stem = Path(filename).stem
    if not stem:
        return normalized

    return (DATA_RUNS_DIR / stem / DEFAULT_RUN_CONFIG_NAME).as_posix()


def resolve_run_config_path(config_path: str, *, repo_root: Path) -> Path:
    repo_root = repo_root.resolve()
    requested = Path(config_path)
    candidate = requested if requested.is_absolute() else repo_root / requested
    resolved = candidate.resolve()

    if resolved.is_dir():
        return (resolved / DEFAULT_RUN_CONFIG_NAME).resolve()

    if resolved.exists():
        return resolved

    normalized_relative = normalize_run_config_path(requested.as_posix())
    if normalized_relative != requested.as_posix():
        fallback = (repo_root / normalized_relative).resolve()
        if fallback.exists():
            return fallback

    return resolved


__all__ = [
    "DATA_RUNS_DIR",
    "DEFAULT_RUN_CONFIG_NAME",
    "iter_run_config_files",
    "normalize_run_config_path",
    "resolve_run_config_path",
]
