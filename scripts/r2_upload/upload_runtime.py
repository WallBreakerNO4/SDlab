# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from .upload_contracts import BucketScope, UploadScriptError


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


def _autoload_dotenv() -> None:
    dotenv_path = find_dotenv(filename=".env", usecwd=True)
    if dotenv_path:
        _ = load_dotenv(dotenv_path=dotenv_path, encoding="utf-8")


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

    cli_workers = int(getattr(args, "concurrency", 1))
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
    concurrency = int(getattr(args, "concurrency", 1))
    if concurrency < 1:
        parser.error("--concurrency 必须 >= 1")

    limit = getattr(args, "limit", None)
    if limit is not None and int(limit) < 1:
        parser.error("--limit 必须 >= 1")
