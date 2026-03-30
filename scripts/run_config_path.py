from __future__ import annotations

from pathlib import Path


DATA_RUNS_DIR = Path("data/runs")
DEFAULT_RUN_CONFIG_NAME = "config.yaml"


def iter_run_config_files(data_runs_dir: Path = DATA_RUNS_DIR) -> list[Path]:
    if not data_runs_dir.exists():
        return []

    config_files: list[Path] = []
    for child in sorted(data_runs_dir.iterdir(), key=lambda path: path.as_posix()):
        if not child.is_dir():
            continue

        config_file = child / DEFAULT_RUN_CONFIG_NAME
        if config_file.is_file():
            config_files.append(config_file)

    return config_files


def resolve_run_config_path(config_path: str, *, repo_root: Path) -> Path:
    repo_root = repo_root.resolve()
    requested = Path(config_path)
    candidate = requested if requested.is_absolute() else repo_root / requested
    resolved = candidate.resolve()

    if resolved.is_dir():
        return (resolved / DEFAULT_RUN_CONFIG_NAME).resolve()

    if resolved.exists():
        return resolved

    return resolved


__all__ = [
    "DATA_RUNS_DIR",
    "DEFAULT_RUN_CONFIG_NAME",
    "iter_run_config_files",
    "resolve_run_config_path",
]
