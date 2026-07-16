# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor

from .r2_client import R2Client
from .supabase_writer import SupabaseWriter
from .upload_contracts import RunPlan, _CATEGORY_CHOICES, _EXIT_CODES_BY_CATEGORY
from .upload_executor import _execute
from .upload_io import _to_json_line
from .upload_planner import _build_plans, _dry_run_summary
from .upload_runtime import (
    _autoload_dotenv,
    _configure_logging,
    _resolve_default_run_root,
    _exit_code_for_exception,
    _require_bucket_names,
    _resolve_image_workers,
    _resolve_intermediate_root,
    _resolve_upload_concurrency,
    _validate_args,
)
from .variants import plan_image_variants

LOG = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload ComfyUI run artifacts to R2 + Supabase."
    )
    _ = parser.add_argument(
        "--run-root",
        default=_resolve_default_run_root(),
        help="Root directory containing run folders.",
    )
    run_group = parser.add_mutually_exclusive_group()
    _ = run_group.add_argument(
        "--run-dir", help="Specific run directory (name or path)."
    )
    _ = run_group.add_argument(
        "--all-runs",
        action="store_true",
        help="Process all runs under --run-root.",
    )
    _ = parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without network or database writes.",
    )
    _ = parser.add_argument(
        "-F",
        "--force-publish",
        action="store_true",
        help="Republish an existing run and replace its current view pointer.",
    )
    _ = parser.add_argument(
        "--category",
        choices=["normal", "advance", "nsfw"],
        help="Optional category override.",
    )
    _ = parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Image planning worker count fallback when R2_IMAGE_WORKERS is unset. Defaults to available CPU count.",
    )
    _ = parser.add_argument(
        "--limit",
        type=int,
        help="Reserved limit for number of images.",
    )
    return parser


def _build_plans_from_args(args: argparse.Namespace) -> list[RunPlan]:
    _ = _CATEGORY_CHOICES
    intermediate_root = _resolve_intermediate_root(args)
    image_workers = _resolve_image_workers(args)
    return _build_plans(
        args,
        intermediate_root=intermediate_root,
        image_workers=image_workers,
        thread_pool_cls=ThreadPoolExecutor,
        plan_image_variants_fn=plan_image_variants,
    )


def _execute_plans(
    plans: list[RunPlan], *, force_publish: bool
) -> dict[str, object]:
    bucket_names = _require_bucket_names()
    upload_concurrency = _resolve_upload_concurrency()
    return _execute(
        plans,
        bucket_names=bucket_names,
        upload_concurrency=upload_concurrency,
        r2_client_factory=lambda: R2Client.from_env(dry_run=False),
        supabase_writer_factory=lambda: SupabaseWriter.from_env(dry_run=False),
        thread_pool_cls=ThreadPoolExecutor,
        force_publish=force_publish,
    )


def main(argv: list[str] | None = None) -> int:
    _autoload_dotenv()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        _validate_args(args, parser)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 1

    try:
        _configure_logging()
        plans = _build_plans_from_args(args)
        dry_run = bool(getattr(args, "dry_run", False))

        if dry_run:
            LOG.info("dry-run mode: no network/database writes")
            summary = _dry_run_summary(plans)
            summary["force_publish"] = bool(args.force_publish)
            print(_to_json_line(summary))
            return 0

        print(
            _to_json_line(
                _execute_plans(plans, force_publish=bool(args.force_publish))
            )
        )
        return 0
    except Exception as exc:
        category = getattr(exc, "category", None)
        error_code = getattr(exc, "code", None)
        error_context = getattr(exc, "context", None)
        exit_code = _exit_code_for_exception(
            exc,
            exit_codes_by_category=_EXIT_CODES_BY_CATEGORY,
        )
        error_payload = {
            "mode": "error",
            "error": exc.__class__.__name__,
            "message": str(exc),
            "exit_code": exit_code,
        }
        if isinstance(category, str):
            error_payload["category"] = category
        if isinstance(error_code, str) and error_code:
            error_payload["code"] = error_code
        if isinstance(error_context, dict):
            error_payload["context"] = dict(error_context)
        print(_to_json_line(error_payload))
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
