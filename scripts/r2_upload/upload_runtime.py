# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from ..env_loading import load_env_files
from .upload_contracts import BucketScope, UploadScriptError


DEFAULT_RUN_ROOT = "outputs"
LOCAL_FLAG = "--local"


def _env_optional_str(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped if stripped else None


def _resolve_default_run_root() -> str:
    return _env_optional_str("COMFYUI_OUT_DIR") or DEFAULT_RUN_ROOT


def _exit_code_for_exception(
    exc: Exception, *, exit_codes_by_category: dict[str, int]
) -> int:
    category = getattr(exc, "category", None)
    if isinstance(category, str):
        return exit_codes_by_category.get(category, 1)
    return 1


def _configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def _autoload_dotenv(*, local: bool = False) -> None:
    load_env_files(local=local)


def _argv_requests_local(argv: list[str] | None) -> bool:
    """在正式解析前判定 `--local`，因为 env 文件必须在 build_parser 之前加载。"""
    probe = argparse.ArgumentParser(add_help=False)
    _ = probe.add_argument(LOCAL_FLAG, action="store_true")
    _ = probe.add_argument("-h", "--help", action="store_true")
    try:
        known, _ = probe.parse_known_args(argv)
    except SystemExit:
        return False
    # 帮助信息不该因为缺少 .env.local-db 而打不开。
    if bool(known.help):
        return False
    return bool(known.local)


def _parse_env_optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError as exc:
        raise UploadScriptError(
            f"环境变量 {name} 不是有效整数: {stripped}",
            category="config",
        ) from exc


def _available_cpu_count() -> int:
    try:
        affinity = os.sched_getaffinity(0)
    except AttributeError:
        affinity = None
    if affinity is not None:
        return max(1, len(affinity))
    return max(1, os.cpu_count() or 1)


def _resolve_intermediate_root(args: argparse.Namespace) -> Path:
    env_value = os.getenv("R2_UPLOAD_INTERMEDIATE_DIR")
    if isinstance(env_value, str) and env_value.strip():
        root = Path(env_value.strip()).expanduser().resolve()
    else:
        run_root = Path(str(args.run_root)).resolve()
        root = (run_root / "_r2_upload_intermediate").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_image_workers(args: argparse.Namespace) -> int:
    env_workers = _parse_env_optional_int("R2_IMAGE_WORKERS")
    if env_workers is not None:
        if env_workers < 1:
            raise UploadScriptError(
                "环境变量 R2_IMAGE_WORKERS 必须 >= 1",
                category="config",
            )
        return env_workers

    cli_workers_raw = getattr(args, "concurrency", None)
    if cli_workers_raw is None:
        return _available_cpu_count()

    cli_workers = int(cli_workers_raw)
    if cli_workers < 1:
        raise UploadScriptError("--concurrency 必须 >= 1", category="argument")
    return cli_workers


def _resolve_upload_concurrency() -> int:
    env_concurrency = _parse_env_optional_int("R2_UPLOAD_CONCURRENCY")
    if env_concurrency is None:
        return 1
    if env_concurrency < 1:
        raise UploadScriptError(
            "环境变量 R2_UPLOAD_CONCURRENCY 必须 >= 1",
            category="config",
        )
    return env_concurrency


def _require_bucket_names() -> dict[BucketScope, str]:
    public_name = os.getenv("R2_PUBLIC_BUCKET")
    private_name = os.getenv("R2_PRIVATE_BUCKET")
    if public_name is None or not public_name.strip():
        raise UploadScriptError(
            "missing required R2 bucket configuration: R2_PUBLIC_BUCKET",
            category="config",
        )
    if private_name is None or not private_name.strip():
        raise UploadScriptError(
            "missing required R2 bucket configuration: R2_PRIVATE_BUCKET",
            category="config",
        )
    return {
        "public": public_name.strip(),
        "private": private_name.strip(),
    }


def _validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if bool(getattr(args, "force_publish", False)) and bool(
        getattr(args, "all_runs", False)
    ):
        parser.error("--force-publish 仅可与单个 --run-dir 一起使用")

    if bool(getattr(args, "complete", False)) and bool(
        getattr(args, "all_runs", False)
    ):
        parser.error("--complete 仅可与单个 --run-dir 一起使用")

    concurrency = getattr(args, "concurrency", None)
    if concurrency is not None and int(concurrency) < 1:
        parser.error("--concurrency 必须 >= 1")

    limit = getattr(args, "limit", None)
    if limit is not None and int(limit) < 1:
        parser.error("--limit 必须 >= 1")
