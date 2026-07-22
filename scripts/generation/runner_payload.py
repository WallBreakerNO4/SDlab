from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any, cast
from datetime import datetime, timezone

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
    workflow_api_path: str | None = (
        workflow_context.workflow_json_path
        if workflow_context is not None
        else args.workflow_json
    )
    workflow_hash = (
        workflow_context.workflow_hash if workflow_context is not None else "not_loaded"
    )
    workflow_api_sha256 = workflow_hash
    if (
        workflow_context is None
        and isinstance(workflow_api_path, str)
        and workflow_api_path
    ):
        workflow_api_sha256 = _sha256_file(Path(workflow_api_path))
    workflow_download_path = getattr(args, "workflow_download_json", None)

    x_path = Path(args.x_json)
    y_path = Path(args.y_json)
    run_key = run_dir.name
    x_descriptions = read_x_descriptions(args.x_json)

    return {
        "run_id": run_key,
        "run_key": run_key,
        "created_at": _now_iso(),
        "dry_run": args.dry_run,
        "run_dir": run_key,
        "backend": getattr(args, "config_backend", "comfyui"),
        "config_schema_version": getattr(args, "config_schema_version", None),
        "config_path": getattr(args, "config_path", None),
        "config_sha256": getattr(args, "config_sha256", None),
        "x_json_path": str(x_path),
        "y_json_path": str(y_path),
        "x_json_sha256": _sha256_file(x_path),
        "y_json_sha256": _sha256_file(y_path),
        "model": _build_model_snapshot(args),
        "template": args.template,
        "quality_prompt": getattr(args, "quality_prompt", None),
        "base_seed": args.base_seed,
        "seed_strategy": "sha256(base_seed:x_index:y_index)[:16] mod 18446744073709519872",
        "workflow_api_path": workflow_api_path,
        "workflow_api_sha256": workflow_api_sha256,
        "workflow_download_path": workflow_download_path,
        "workflow_download_sha256": (
            _sha256_file(Path(workflow_download_path))
            if isinstance(workflow_download_path, str) and workflow_download_path
            else None
        ),
        "workflow_status": workflow_status,
        "selected_ksampler_node_id": (
            workflow_context.selected_ksampler_id
            if workflow_context is not None
            else None
        ),
        "comfyui_base_url": args.base_url,
        "request_timeout_s": args.request_timeout_s,
        "download_read_timeout_s": getattr(args, "download_read_timeout_s", None),
        "job_timeout_s": args.job_timeout_s,
        "concurrency": args.concurrency,
        "download_concurrency": getattr(args, "download_concurrency", None),
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
            "append_negative_prompt": getattr(args, "append_negative_prompt", None),
            "width": args.width,
            "height": args.height,
            "batch_size": args.batch_size,
            "steps": args.steps,
            "cfg": args.cfg,
            "denoise": args.denoise,
            "sampler_name": args.sampler_name,
            "scheduler": args.scheduler,
        },
        "assets": _build_assets_snapshot(args),
        "config_snapshot": _build_config_snapshot(args),
    }



def _build_model_snapshot(args: argparse.Namespace) -> dict[str, object] | None:
    model = cast(Any, getattr(args, "config_model", None))
    if model is None:
        return None

    return {
        "key": model.key,
        "name": model.name,
        "family": model.family,
        "artist_weight_profile": getattr(model, "artist_weight_profile", "identity"),
        "links": dict(model.links),
        "description": dict(model.description),
    }


def _build_config_snapshot(args: argparse.Namespace) -> dict[str, object] | None:
    prompts_obj = getattr(args, "config_prompts", None)
    workflow_obj = getattr(args, "config_workflow", None)
    generation_obj = getattr(args, "config_generation", None)
    selection_obj = getattr(args, "config_selection", None)
    if any(
        value is None
        for value in (prompts_obj, workflow_obj, generation_obj, selection_obj)
    ):
        return None

    prompts = cast(Any, prompts_obj)
    workflow = cast(Any, workflow_obj)
    generation = cast(Any, generation_obj)
    selection = cast(Any, selection_obj)
    return {
        "prompts": {
            "x_path": prompts.x.repo_relative_path,
            "y_path": prompts.y.repo_relative_path,
            "x_sha256": prompts.x.sha256,
            "y_sha256": prompts.y.sha256,
        },
        "workflow": {
            "api_path": workflow.repo_relative_path,
            "api_sha256": workflow.sha256,
            "download_path": (
                workflow.download.repo_relative_path
                if workflow.download is not None
                else None
            ),
            "download_sha256": (
                workflow.download.sha256 if workflow.download is not None else None
            ),
            "ksampler_node_id": workflow.ksampler_node_id,
            "anima_artist_mixer": getattr(
                workflow,
                "anima_artist_mixer",
                False,
            ),
        },
        "generation": {
            "template": generation.template,
            "quality_prompt": generation.quality_prompt,
            "base_seed": generation.base_seed,
            "negative_prompt": generation.negative_prompt,
            "append_negative_prompt": generation.append_negative_prompt,
            "width": generation.width,
            "height": generation.height,
            "batch_size": generation.batch_size,
            "steps": generation.steps,
            "cfg": generation.cfg,
            "denoise": generation.denoise,
            "sampler_name": generation.sampler_name,
            "scheduler": generation.scheduler,
        },
        "selection": {
            "x_limit": selection.x_limit,
            "y_limit": selection.y_limit,
            "x_indexes": selection.x_indexes,
            "y_indexes": selection.y_indexes,
        },
    }


def _build_assets_snapshot(args: argparse.Namespace) -> dict[str, object] | None:
    assets_obj = getattr(args, "run_assets", None)
    if assets_obj is None:
        return None

    assets = cast(Any, assets_obj)
    return _build_asset_collection_payload(
        cover_image=assets.cover_image,
        homepage_images=assets.homepage_images,
        include_absolute_path=False,
    )


def _build_asset_collection_payload(
    *,
    cover_image: Any,
    homepage_images: list[Any],
    include_absolute_path: bool,
) -> dict[str, object]:
    return {
        "cover_image": _build_asset_ref_payload(
            cover_image,
            include_absolute_path=include_absolute_path,
        ),
        "homepage_images": [
            _build_asset_ref_payload(
                asset,
                include_absolute_path=include_absolute_path,
            )
            for asset in homepage_images
        ],
    }


def _build_asset_ref_payload(
    asset: Any, *, include_absolute_path: bool
) -> dict[str, object] | None:
    if asset is None:
        return None

    payload: dict[str, object] = {
        "repo_relative_path": asset.repo_relative_path,
        "sha256": asset.sha256,
    }
    if include_absolute_path:
        payload["path"] = asset.path
    return payload


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
