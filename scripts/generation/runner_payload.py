from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any
import uuid

from scripts.generation.prompt_grid import read_x_descriptions
from scripts.generation.runner_selection import _extract_x_info_type


def _build_run_payload(
    args: argparse.Namespace,
    run_dir: Path,
    x_selected: list[Any],
    y_selected: list[Any],
    workflow_context: Any,
) -> dict[str, object]:
    workflow_status = "loaded" if workflow_context is not None else "not_loaded"
    workflow_json_path: str | None = (
        workflow_context.workflow_json_path
        if workflow_context is not None
        else args.workflow_json
    )
    workflow_hash = (
        workflow_context.workflow_hash if workflow_context is not None else "not_loaded"
    )

    x_path = Path(args.x_json)
    y_path = Path(args.y_json)
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    x_descriptions = read_x_descriptions(args.x_json)

    return {
        "run_id": run_id,
        "created_at": _now_iso(),
        "dry_run": args.dry_run,
        "run_dir": str(run_dir),
        "x_json_path": str(x_path),
        "y_json_path": str(y_path),
        "x_json_sha256": _sha256_file(x_path),
        "y_json_sha256": _sha256_file(y_path),
        "template": args.template,
        "base_seed": args.base_seed,
        "seed_strategy": "sha256(base_seed:x_index:y_index)[:16] mod 18446744073709519872",
        "workflow_json_path": workflow_json_path,
        "workflow_json_sha256": workflow_hash,
        "workflow_status": workflow_status,
        "selected_ksampler_node_id": (
            workflow_context.selected_ksampler_id
            if workflow_context is not None
            else None
        ),
        "comfyui_base_url": args.base_url,
        "request_timeout_s": args.request_timeout_s,
        "job_timeout_s": args.job_timeout_s,
        "concurrency": args.concurrency,
        "client_id": args.client_id,
        "selection": {
            "x_indexes": [item.index for item in x_selected],
            "y_indexes": [item.index for item in y_selected],
            "x_count": len(x_selected),
            "y_count": len(y_selected),
            "total_cells": len(x_selected) * len(y_selected),
            "x_columns": [
                {
                    "x_index": item.index,
                    "type": _extract_x_info_type(item.value),
                    "description": x_descriptions[item.index]
                    if item.index < len(x_descriptions)
                    else {"zh": "", "en": ""},
                }
                for item in x_selected
            ],
            "x_limit": args.x_limit,
            "y_limit": args.y_limit,
            "x_indexes_raw": args.x_indexes,
            "y_indexes_raw": args.y_indexes,
        },
        "generation_overrides": {
            "negative_prompt": args.negative_prompt,
            "width": args.width,
            "height": args.height,
            "batch_size": args.batch_size,
            "steps": args.steps,
            "cfg": args.cfg,
            "denoise": args.denoise,
            "sampler_name": args.sampler_name,
            "scheduler": args.scheduler,
        },
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
