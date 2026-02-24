# pyright: basic, reportUnusedCallResult=false, reportImplicitStringConcatenation=false

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

if __package__ in {None, ""}:
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from scripts.generation.comfyui_client import (  # noqa: E402
    ComfyUIClientError,
    comfy_download_image_to_path,
    comfy_get_history_item,
    comfy_submit_prompt,
    comfy_wait_prompt_done_with_fallback,
)
from scripts.generation.prompt_grid import (  # noqa: E402
    compute_prompt_hash,
    derive_seed,
    read_x_descriptions,
    read_x_rows,
    read_y_rows,
    render_positive_prompt,
)
from scripts.generation.retry_failed_selection import (  # noqa: E402
    select_failed_and_incomplete_cells,
)
from scripts.generation.run_replay import (  # noqa: E402
    load_run_replay_config,
)
from scripts.generation.runner_env import (  # noqa: E402
    _autoload_dotenv,
    _env_append_negative_prompt,
    _env_bool,
    _env_float,
    _env_optional_float,
    _env_optional_int,
    _env_str,
    _resolve_append_negative_prompt,
)
from scripts.generation.runner_selection import (  # noqa: E402
    SelectedRow,
    _extract_x_info_type,
    _parse_indexes,
    _select_rows,
    _select_rows_by_fixed_indexes,
)
from scripts.generation.output_packager import (  # noqa: E402
    RunArtifacts,
    _MetadataWriter,
    _ensure_newline_terminated,
    _load_latest_metadata_records,
    _load_latest_metadata_records_strict,
    _metadata_writer,
    _prepare_existing_run_artifacts,
    _prepare_run_artifacts,
)
from scripts.generation.runner_coordinator import (  # noqa: E402
    RunStats,
    _CellPlan,
    _DownloadRequest,
    _GenOutcome,
    _build_local_image_paths as _coordinator_build_local_image_paths,
    _collect_remote_images as _coordinator_collect_remote_images,
    _fetch_remote_images_with_retry as _coordinator_fetch_remote_images_with_retry,
    _infer_image_extension as _coordinator_infer_image_extension,
    _serialize_error as _coordinator_serialize_error,
    _worker_fetch_and_download as _coordinator_worker_fetch_and_download,
    _worker_submit_and_wait as _coordinator_worker_submit_and_wait,
    run_generation,
)
from scripts.generation.runner_retry import (  # noqa: E402
    _apply_replay_config_to_args,
    _build_retry_target_cells,
    _extract_retry_error_code,
    _filter_retry_failed_cells,
    _parse_retry_error_codes,
    _validate_retry_failed_cells_consistency,
)
from scripts.generation.workflow_patch import (  # noqa: E402
    WorkflowDict,
    WorkflowOverrides,
    load_workflow,
    patch_workflow,
)

DEFAULT_X_JSON = "data/prompts/X/common_prompts.json"
DEFAULT_Y_JSON = "data/prompts/Y/300_NAI_Styles_Table-test.json"
DEFAULT_TEMPLATE = "{gender}{characters}{series}{rating}{y}{general}{quality}"
DEFAULT_WORKFLOW_JSON = "data/comfyui-flow/CKNOOBRF.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8188"
DEFAULT_REQUEST_TIMEOUT_S = 30.0
DEFAULT_JOB_TIMEOUT_S = 600.0
LOG = logging.getLogger(__name__)

ALLOWED_TEMPLATE_KEYS = {
    "gender",
    "characters",
    "series",
    "rating",
    "y",
    "general",
    "quality",
}
TEMPLATE_TOKEN_RE = re.compile(r"\{([a-z_]+)\}")


@dataclass(slots=True)
class WorkflowContext:
    workflow: WorkflowDict
    workflow_json_path: str
    workflow_hash: str
    selected_ksampler_id: str
    default_negative_prompt: str
    default_params: dict[str, object | None]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="遍历 X/Y prompts 网格，调用 ComfyUI 生图并落盘 metadata。"
    )

    parser.add_argument(
        "--x-json", default=_env_str("COMFYUI_X_JSON") or DEFAULT_X_JSON
    )
    parser.add_argument(
        "--y-json", default=_env_str("COMFYUI_Y_JSON") or DEFAULT_Y_JSON
    )
    parser.add_argument(
        "--template",
        default=_env_str("COMFYUI_TEMPLATE") or DEFAULT_TEMPLATE,
    )
    parser.add_argument(
        "--base-seed",
        type=int,
        default=_env_optional_int("COMFYUI_BASE_SEED") or 0,
    )
    parser.add_argument(
        "--workflow-json",
        default=_env_str("COMFYUI_WORKFLOW_JSON") or DEFAULT_WORKFLOW_JSON,
    )
    parser.add_argument(
        "--ksampler-node-id",
        default=_env_str("COMFYUI_KSAMPLER_NODE_ID"),
    )

    parser.add_argument(
        "--x-limit",
        type=int,
        default=_env_optional_int("COMFYUI_X_LIMIT"),
    )
    parser.add_argument(
        "--y-limit",
        type=int,
        default=_env_optional_int("COMFYUI_Y_LIMIT"),
    )
    parser.add_argument(
        "--x-indexes",
        default=_env_str("COMFYUI_X_INDEXES"),
    )
    parser.add_argument(
        "--y-indexes",
        default=_env_str("COMFYUI_Y_INDEXES"),
    )

    parser.add_argument(
        "--run-dir",
        default=_env_str("COMFYUI_RUN_DIR"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=_env_bool("COMFYUI_DRY_RUN", default=False),
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        default=_env_bool("COMFYUI_RETRY_FAILED", default=False),
    )
    parser.add_argument(
        "--retry-incomplete",
        action="store_true",
        default=_env_bool("COMFYUI_RETRY_INCOMPLETE", default=False),
    )
    parser.add_argument(
        "--retry-error-code",
        default=_env_str("COMFYUI_RETRY_ERROR_CODE"),
    )

    parser.add_argument(
        "--base-url",
        default=(_env_str("COMFYUI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
    )
    parser.add_argument(
        "--request-timeout-s",
        type=float,
        default=_env_float("COMFYUI_REQUEST_TIMEOUT_S", DEFAULT_REQUEST_TIMEOUT_S),
    )
    parser.add_argument(
        "--job-timeout-s",
        type=float,
        default=_env_float("COMFYUI_JOB_TIMEOUT_S", DEFAULT_JOB_TIMEOUT_S),
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=_env_optional_int("COMFYUI_CONCURRENCY") or 1,
    )
    parser.add_argument("--client-id", default=_env_str("COMFYUI_CLIENT_ID"))

    parser.add_argument(
        "--negative-prompt",
        default=_env_str("COMFYUI_NEGATIVE_PROMPT"),
    )
    parser.add_argument("--width", type=int, default=_env_optional_int("COMFYUI_WIDTH"))
    parser.add_argument(
        "--height", type=int, default=_env_optional_int("COMFYUI_HEIGHT")
    )
    parser.add_argument(
        "--batch-size", type=int, default=_env_optional_int("COMFYUI_BATCH_SIZE")
    )
    parser.add_argument("--steps", type=int, default=_env_optional_int("COMFYUI_STEPS"))
    parser.add_argument("--cfg", type=float, default=_env_optional_float("COMFYUI_CFG"))
    parser.add_argument(
        "--denoise", type=float, default=_env_optional_float("COMFYUI_DENOISE")
    )
    parser.add_argument(
        "--sampler-name",
        default=_env_str("COMFYUI_SAMPLER_NAME"),
    )
    parser.add_argument("--scheduler", default=_env_str("COMFYUI_SCHEDULER"))

    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        _autoload_dotenv()
        parser = build_parser()
    except ValueError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    args = parser.parse_args(argv)

    try:
        if _is_retry_mode(args):
            return run_retry(args)
        return run(args)
    except ValueError as exc:
        print(f"参数错误: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"运行失败: {exc}", file=sys.stderr)
        return 2


def _is_retry_mode(args: argparse.Namespace) -> bool:
    return bool(args.retry_failed or args.retry_incomplete)


def run(args: argparse.Namespace) -> int:
    _validate_args(args)
    _configure_logging()

    x_rows = read_x_rows(args.x_json)
    y_rows = read_y_rows(args.y_json)
    x_descriptions = read_x_descriptions(args.x_json)

    x_selected = _select_rows(
        rows=x_rows,
        limit=args.x_limit,
        indexes_raw=args.x_indexes,
        axis_name="x",
    )
    y_selected = _select_rows(
        rows=y_rows,
        limit=args.y_limit,
        indexes_raw=args.y_indexes,
        axis_name="y",
    )

    run_artifacts = _prepare_run_artifacts(args.run_dir)
    run_artifacts.images_dir.mkdir(parents=True, exist_ok=True)

    workflow_context = _load_workflow_context(args)
    workflow_hash = (
        workflow_context.workflow_hash if workflow_context is not None else "not_loaded"
    )

    run_payload = _build_run_payload(
        args=args,
        run_dir=run_artifacts.run_dir,
        x_selected=x_selected,
        y_selected=y_selected,
        workflow_context=workflow_context,
    )

    run_id_obj = run_payload.get("run_id")
    if not isinstance(run_id_obj, str) or not run_id_obj:
        raise ValueError("run payload missing run_id")
    run_id = run_id_obj
    run_artifacts.run_json_path.write_text(
        json.dumps(run_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    total_cells = len(x_selected) * len(y_selected)
    example_prompt = _build_example_prompt(args.template, x_selected, y_selected)
    if args.dry_run:
        print(f"组合总数: {total_cells}")
        print(f"示例正向提示词: {example_prompt}")

    latest_records = _load_latest_metadata_records(run_artifacts.metadata_path)

    stats = RunStats()

    LOG.info(
        "开始运行: total_cells=%s dry_run=%s run_dir=%s",
        total_cells,
        args.dry_run,
        run_artifacts.run_dir,
    )

    with logging_redirect_tqdm():
        with tqdm(
            total=total_cells,
            desc="生成进度",
            unit="cell",
            dynamic_ncols=True,
        ) as pbar:
            with _metadata_writer(run_artifacts.metadata_path) as writer:
                has_failed = run_generation(
                    args=args,
                    x_selected=x_selected,
                    y_selected=y_selected,
                    x_descriptions=x_descriptions,
                    latest_records=latest_records,
                    run_dir=run_artifacts.run_dir,
                    run_id=run_id,
                    workflow_context=workflow_context,
                    workflow_hash=workflow_hash,
                    stats=stats,
                    pbar=pbar,
                    writer=writer,
                    render_prompt=_render_prompt_by_template,
                    compute_prompt_hash=compute_prompt_hash,
                    derive_seed=derive_seed,
                    effective_generation_params=_effective_generation_params,
                    next_attempt=lambda prev, increment: _next_attempt(
                        prev,
                        increment=increment,
                    ),
                    should_resume_skip=lambda existing,
                    expected_prompt_hash,
                    expected_seed,
                    expected_workflow_hash: _should_resume_skip(
                        existing=existing,
                        run_dir=run_artifacts.run_dir,
                        expected_prompt_hash=expected_prompt_hash,
                        expected_seed=expected_seed,
                        expected_workflow_hash=expected_workflow_hash,
                    ),
                    build_base_metadata_record=_build_base_metadata_record,
                    extract_local_image_path=_extract_local_image_path,
                    extract_local_image_paths=_extract_local_image_paths,
                    now_iso=_now_iso,
                    patch_workflow=patch_workflow,
                    workflow_overrides_factory=WorkflowOverrides,
                    final_negative_prompt_for_x_row=_final_negative_prompt_for_x_row,
                    submit_prompt=comfy_submit_prompt,
                    wait_prompt_done_with_fallback=comfy_wait_prompt_done_with_fallback,
                    get_history_item=comfy_get_history_item,
                    download_image_to_path=comfy_download_image_to_path,
                )

    print(
        "结果统计: "
        f"success={stats.success}, skipped={stats.skipped}, "
        f"failed={stats.failed}, resume_hit={stats.resume_hit}"
    )

    return 1 if has_failed else 0


def run_retry(args: argparse.Namespace) -> int:
    _validate_args(args)
    _configure_logging()

    run_artifacts = _prepare_existing_run_artifacts(args.run_dir)
    run_artifacts.images_dir.mkdir(parents=True, exist_ok=True)
    replay = load_run_replay_config(run_artifacts.run_dir, strict_sha256=True)
    _apply_replay_config_to_args(args, replay)

    x_rows = read_x_rows(args.x_json)
    y_rows = read_y_rows(args.y_json)
    x_descriptions = read_x_descriptions(args.x_json)

    x_selected = _select_rows_by_fixed_indexes(
        rows=x_rows,
        indexes=replay.selection.x_indexes,
        axis_name="x",
    )
    y_selected = _select_rows_by_fixed_indexes(
        rows=y_rows,
        indexes=replay.selection.y_indexes,
        axis_name="y",
    )

    workflow_context = _load_workflow_context(args)
    workflow_hash = (
        workflow_context.workflow_hash if workflow_context is not None else "not_loaded"
    )

    expected_cells = {
        (x_item.index, y_item.index) for x_item in x_selected for y_item in y_selected
    }
    selection = select_failed_and_incomplete_cells(
        metadata_path=run_artifacts.metadata_path,
        run_dir=run_artifacts.run_dir,
        expected_cells=expected_cells,
    )
    latest_records = _load_latest_metadata_records_strict(run_artifacts.metadata_path)

    retry_error_codes = _parse_retry_error_codes(args.retry_error_code)
    failed_cells = _filter_retry_failed_cells(
        failed_cells=selection.failed_cells,
        latest_records=latest_records,
        retry_error_codes=retry_error_codes,
    )
    target_cells = _build_retry_target_cells(
        retry_failed=args.retry_failed,
        retry_incomplete=args.retry_incomplete,
        failed_cells=failed_cells,
        incomplete_cells=selection.incomplete_cells,
    )

    x_rows_by_index = {item.index: item.value for item in x_selected}
    y_values_by_index = {item.index: item.value.get("y", "") for item in y_selected}
    _validate_retry_failed_cells_consistency(
        target_cells=target_cells,
        latest_records=latest_records,
        x_rows_by_index=x_rows_by_index,
        y_values_by_index=y_values_by_index,
        template=args.template,
        base_seed=args.base_seed,
        workflow_hash=workflow_hash,
        render_prompt=_render_prompt_by_template,
        compute_prompt_hash=compute_prompt_hash,
        derive_seed=derive_seed,
        coerce_int_or_none=_coerce_int_or_none,
    )

    total_cells = len(target_cells)
    stats = RunStats()

    x_by_index = {item.index: item for item in x_selected}
    y_by_index = {item.index: item for item in y_selected}
    cell_pairs = [
        (x_by_index[x_index], y_by_index[y_index]) for x_index, y_index in target_cells
    ]

    LOG.info(
        "重试运行: retry_failed=%s retry_incomplete=%s total_cells=%s run_dir=%s",
        args.retry_failed,
        args.retry_incomplete,
        total_cells,
        run_artifacts.run_dir,
    )

    with logging_redirect_tqdm():
        with tqdm(
            total=total_cells,
            desc="重试进度",
            unit="cell",
            dynamic_ncols=True,
        ) as pbar:
            with _metadata_writer(run_artifacts.metadata_path) as writer:
                has_failed = run_generation(
                    args=args,
                    x_selected=x_selected,
                    y_selected=y_selected,
                    x_descriptions=x_descriptions,
                    latest_records=latest_records,
                    run_dir=run_artifacts.run_dir,
                    run_id=run_artifacts.run_dir.name,
                    workflow_context=workflow_context,
                    workflow_hash=workflow_hash,
                    stats=stats,
                    pbar=pbar,
                    writer=writer,
                    render_prompt=_render_prompt_by_template,
                    compute_prompt_hash=compute_prompt_hash,
                    derive_seed=derive_seed,
                    effective_generation_params=_effective_generation_params,
                    next_attempt=lambda prev, increment: _next_attempt(
                        prev,
                        increment=increment,
                    ),
                    should_resume_skip=lambda existing,
                    expected_prompt_hash,
                    expected_seed,
                    expected_workflow_hash: False,
                    build_base_metadata_record=_build_base_metadata_record,
                    extract_local_image_path=_extract_local_image_path,
                    extract_local_image_paths=_extract_local_image_paths,
                    now_iso=_now_iso,
                    patch_workflow=patch_workflow,
                    workflow_overrides_factory=WorkflowOverrides,
                    final_negative_prompt_for_x_row=_final_negative_prompt_for_x_row,
                    submit_prompt=comfy_submit_prompt,
                    wait_prompt_done_with_fallback=comfy_wait_prompt_done_with_fallback,
                    get_history_item=comfy_get_history_item,
                    download_image_to_path=comfy_download_image_to_path,
                    cell_pairs=cell_pairs,
                    save_image_prefix_builder=lambda run_id,
                    x_index,
                    y_index,
                    seed,
                    prompt_hash: (
                        f"{run_artifacts.run_dir.name}/"
                        f"retry-x{x_index}-y{y_index}-s{seed}-{prompt_hash[:8]}"
                    ),
                )

    print(
        "结果统计: "
        f"success={stats.success}, skipped={stats.skipped}, "
        f"failed={stats.failed}, resume_hit={stats.resume_hit}"
    )

    return 1 if has_failed else 0


def _configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def _validate_args(args: argparse.Namespace) -> None:
    retry_mode = _is_retry_mode(args)

    if args.request_timeout_s <= 0:
        raise ValueError("--request-timeout-s 必须 > 0")
    if args.job_timeout_s <= 0:
        raise ValueError("--job-timeout-s 必须 > 0")
    if args.x_limit is not None and args.x_limit < 0:
        raise ValueError("--x-limit 不能小于 0")
    if args.y_limit is not None and args.y_limit < 0:
        raise ValueError("--y-limit 不能小于 0")

    if args.concurrency <= 0:
        raise ValueError("--concurrency 必须 > 0")

    retry_error_codes = _parse_retry_error_codes(args.retry_error_code)
    if retry_error_codes is not None and not retry_mode:
        raise ValueError(
            "--retry-error-code 仅可与 --retry-failed/--retry-incomplete 一起使用"
        )

    if retry_mode:
        if not args.run_dir:
            raise ValueError("retry 模式必须提供 --run-dir，且指向已有 run 目录")
        run_dir = Path(args.run_dir)
        if not run_dir.exists() or not run_dir.is_dir():
            raise ValueError(f"retry 模式 --run-dir 不存在或不是目录: {run_dir}")

    if not args.dry_run and not retry_mode:
        if not args.workflow_json:
            raise ValueError("非 dry-run 模式必须提供 --workflow-json")

    if not args.client_id:
        args.client_id = str(uuid.uuid4())


def _append_negative_prompt(base: str | None, append: str | None) -> str:
    """纯函数：拼接 base negative prompt 和 append negative prompt。

    Args:
        base: 基础负面提示词，None 视为空字符串
        append: 追加负面提示词，None 视为空字符串

    Returns:
        拼接后的负面提示词
    """
    if base is None:
        base = ""
    if append is None:
        append = ""

    base_stripped = base.strip()
    append_stripped = append.strip()

    if not base_stripped:
        return append_stripped.lstrip(", ").lstrip(",")

    if not append_stripped:
        return base_stripped

    append_cleaned = append_stripped.lstrip(", ").lstrip(",")

    if not append_cleaned:
        return base_stripped

    if base_stripped.endswith(","):
        delimiter = " "
    else:
        delimiter = ", "

    return base_stripped + delimiter + append_cleaned


def _load_workflow_context(args: argparse.Namespace) -> WorkflowContext | None:
    if args.dry_run:
        return None

    workflow_json_path = args.workflow_json
    if not workflow_json_path:
        raise ValueError("非 dry-run 模式缺少 workflow 路径")

    workflow_path = Path(workflow_json_path)
    if not workflow_path.exists() or not workflow_path.is_file():
        raise ValueError(f"workflow 文件不存在: {workflow_json_path}")

    workflow = load_workflow(workflow_path)
    workflow_hash = _sha256_file(workflow_path)
    selected_ksampler_id = _resolve_ksampler_id(workflow, args.ksampler_node_id)

    defaults = _extract_workflow_defaults(workflow, selected_ksampler_id)
    default_negative_prompt_obj = defaults.get("negative_prompt")
    default_negative_prompt = (
        default_negative_prompt_obj
        if isinstance(default_negative_prompt_obj, str)
        else ""
    )

    try:
        _ = patch_workflow(
            workflow,
            positive_prompt="__workflow_validation_positive__",
            negative_prompt=default_negative_prompt,
            overrides=WorkflowOverrides(seed=0),
            ksampler_node_id=selected_ksampler_id,
        )
    except Exception as exc:
        raise ValueError(
            "workflow 结构不符合 CLIPTextEncode 注入要求，请使用 CLIPTextEncode 版 workflow"
        ) from exc

    return WorkflowContext(
        workflow=workflow,
        workflow_json_path=str(workflow_path),
        workflow_hash=workflow_hash,
        selected_ksampler_id=selected_ksampler_id,
        default_negative_prompt=default_negative_prompt,
        default_params=defaults,
    )


def _resolve_ksampler_id(workflow: WorkflowDict, requested: str | None) -> str:
    candidates = [
        node_id
        for node_id, node in workflow.items()
        if isinstance(node, dict) and node.get("class_type") == "KSampler"
    ]

    if not candidates:
        raise ValueError("workflow 中未找到 KSampler")

    if requested is not None:
        node_id = str(requested)
        if node_id not in workflow:
            raise ValueError(f"KSampler 节点不存在: {node_id}")
        node = workflow[node_id]
        if node.get("class_type") != "KSampler":
            class_type = node.get("class_type")
            raise ValueError(f"节点 {node_id} 不是 KSampler (class_type={class_type})")
        return node_id

    if len(candidates) > 1:
        details = ", ".join(
            _format_node_title(workflow, node_id) for node_id in candidates
        )
        raise ValueError(
            f"workflow 中存在多个 KSampler；请传入 --ksampler-node-id；可选: {details}"
        )

    return candidates[0]


def _format_node_title(workflow: WorkflowDict, node_id: str) -> str:
    node = workflow.get(node_id, {})
    meta_obj = node.get("_meta") if isinstance(node, dict) else None
    if isinstance(meta_obj, dict):
        title_obj = meta_obj.get("title")
        if isinstance(title_obj, str) and title_obj:
            return f"{node_id} ({title_obj})"
    return f"{node_id} (<no title>)"


def _extract_workflow_defaults(
    workflow: WorkflowDict,
    ksampler_id: str,
) -> dict[str, object | None]:
    node = workflow.get(ksampler_id)
    if not isinstance(node, dict):
        raise ValueError(f"KSampler 节点无效: {ksampler_id}")
    node_inputs = _as_dict(node.get("inputs"))

    negative_node_id = _extract_ref_node_id(node_inputs.get("negative"), "negative")
    latent_node_id = _extract_ref_node_id(
        node_inputs.get("latent_image"), "latent_image"
    )

    negative_node = _as_dict(workflow.get(negative_node_id))
    if negative_node.get("class_type") != "CLIPTextEncode":
        class_type = negative_node.get("class_type")
        raise ValueError(f"负向节点必须是 CLIPTextEncode，当前为: {class_type}")
    negative_inputs = _as_dict(negative_node.get("inputs"))
    negative_prompt_obj = negative_inputs.get("text")
    negative_prompt = (
        negative_prompt_obj if isinstance(negative_prompt_obj, str) else None
    )

    latent_node = _as_dict(workflow.get(latent_node_id))
    if latent_node.get("class_type") != "EmptyLatentImage":
        class_type = latent_node.get("class_type")
        raise ValueError(f"latent 节点必须是 EmptyLatentImage，当前为: {class_type}")
    latent_inputs = _as_dict(latent_node.get("inputs"))

    return {
        "negative_prompt": negative_prompt,
        "width": _coerce_int_or_none(latent_inputs.get("width")),
        "height": _coerce_int_or_none(latent_inputs.get("height")),
        "batch_size": _coerce_int_or_none(latent_inputs.get("batch_size")),
        "steps": _coerce_int_or_none(node_inputs.get("steps")),
        "cfg": _coerce_float_or_none(node_inputs.get("cfg")),
        "denoise": _coerce_float_or_none(node_inputs.get("denoise")),
        "sampler_name": _coerce_str_or_none(node_inputs.get("sampler_name")),
        "scheduler": _coerce_str_or_none(node_inputs.get("scheduler")),
    }


def _extract_ref_node_id(value: object, input_name: str) -> str:
    if not isinstance(value, list) or not value:
        raise ValueError(f"workflow 引用字段无效: inputs.{input_name}")
    first = value[0]
    if not isinstance(first, str) or not first:
        raise ValueError(f"workflow 引用节点 ID 无效: inputs.{input_name}")
    return first


def _build_run_payload(
    args: argparse.Namespace,
    run_dir: Path,
    x_selected: list[SelectedRow],
    y_selected: list[SelectedRow],
    workflow_context: WorkflowContext | None,
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


def _build_example_prompt(
    template: str,
    x_selected: list[SelectedRow],
    y_selected: list[SelectedRow],
) -> str:
    if not x_selected or not y_selected:
        return ""
    first_x = x_selected[0].value
    first_y = y_selected[0].value.get("y", "")
    return _render_prompt_by_template(template, first_x, first_y)


def _render_prompt_by_template(
    template: str,
    x_row: dict[str, str],
    y_value: str,
) -> str:
    if template == DEFAULT_TEMPLATE:
        return render_positive_prompt(x_row, y_value)

    key_map = {
        "gender": x_row.get("gender", ""),
        "characters": x_row.get("characters", ""),
        "series": x_row.get("series", ""),
        "rating": x_row.get("rating", ""),
        "y": y_value,
        "general": x_row.get("general", ""),
        "quality": x_row.get("quality", ""),
    }

    stripped = TEMPLATE_TOKEN_RE.sub("", template)
    if stripped.strip():
        raise ValueError("--template 仅支持由占位符组成，例如 {gender}{y}{quality}")

    rendered: list[str] = []
    for match in TEMPLATE_TOKEN_RE.finditer(template):
        key = match.group(1)
        if key not in ALLOWED_TEMPLATE_KEYS:
            raise ValueError(f"--template 包含未知占位符: {{{key}}}")
        segment = key_map[key].strip()
        if not segment:
            continue
        if not segment.endswith(","):
            segment = f"{segment},"
        rendered.append(segment)
    return "".join(rendered)


def _should_resume_skip(
    existing: dict[str, object] | None,
    run_dir: Path,
    expected_prompt_hash: str,
    expected_seed: int,
    expected_workflow_hash: str,
) -> bool:
    if existing is None:
        return False

    status = existing.get("status")
    if status not in {"success", "skipped"}:
        return False

    prompt_hash = existing.get("prompt_hash")
    if prompt_hash != expected_prompt_hash:
        return False

    seed = _coerce_int_or_none(existing.get("seed"))
    if seed != expected_seed:
        return False

    workflow_hash = existing.get("workflow_hash")
    if not isinstance(workflow_hash, str) or not workflow_hash:
        legacy_hash = existing.get("workflow_json_sha256")
        workflow_hash = legacy_hash if isinstance(legacy_hash, str) else None
    if workflow_hash != expected_workflow_hash:
        return False

    local_image_paths = _extract_local_image_paths(existing)
    if local_image_paths is not None:
        for local_image_path in local_image_paths:
            image_path = Path(local_image_path)
            if not image_path.is_absolute():
                image_path = run_dir / image_path
            if not (image_path.exists() and image_path.is_file()):
                return False
        return True

    local_image_path = _extract_local_image_path(existing)
    if local_image_path is None:
        return False

    image_path = Path(local_image_path)
    if not image_path.is_absolute():
        image_path = run_dir / image_path
    return image_path.exists() and image_path.is_file()


def _extract_local_image_path(existing: dict[str, object] | None) -> str | None:
    if existing is None:
        return None
    local_image_path = existing.get("local_image_path")
    if isinstance(local_image_path, str) and local_image_path.strip():
        return local_image_path
    return None


def _extract_local_image_paths(existing: dict[str, object] | None) -> list[str] | None:
    if existing is None:
        return None
    value = existing.get("local_image_paths")
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


def _effective_negative_prompt(
    args: argparse.Namespace,
    workflow_context: WorkflowContext | None,
) -> str | None:
    if args.negative_prompt is not None:
        return args.negative_prompt
    if workflow_context is None:
        return None
    return workflow_context.default_negative_prompt


def _final_negative_prompt_for_x_row(
    args: argparse.Namespace,
    workflow_context: WorkflowContext | None,
    x_row: dict[str, str],
) -> str | None:
    base_negative_prompt = _effective_negative_prompt(args, workflow_context)
    if base_negative_prompt is None:
        return None

    if _extract_x_info_type(x_row) != "normal":
        return base_negative_prompt

    return _append_negative_prompt(base_negative_prompt, _env_append_negative_prompt())


def _effective_generation_params(
    args: argparse.Namespace,
    workflow_context: WorkflowContext | None,
    x_row: dict[str, str],
    seed: int,
) -> dict[str, object | None]:
    defaults = workflow_context.default_params if workflow_context is not None else {}

    def pick(key: str, override: object | None) -> object | None:
        if override is not None:
            return override
        return defaults.get(key)

    negative_prompt = _final_negative_prompt_for_x_row(args, workflow_context, x_row)

    return {
        "seed": seed,
        "negative_prompt": negative_prompt,
        "width": pick("width", args.width),
        "height": pick("height", args.height),
        "batch_size": pick("batch_size", args.batch_size),
        "steps": pick("steps", args.steps),
        "cfg": pick("cfg", args.cfg),
        "denoise": pick("denoise", args.denoise),
        "sampler_name": pick("sampler_name", args.sampler_name),
        "scheduler": pick("scheduler", args.scheduler),
    }


def _next_attempt(prev: dict[str, object] | None, *, increment: bool) -> int:
    if prev is None:
        return 1

    raw_attempt = _coerce_int_or_none(prev.get("attempt"))
    previous_attempt = raw_attempt if raw_attempt is not None and raw_attempt > 0 else 1
    if increment:
        return previous_attempt + 1
    return previous_attempt


def _build_base_metadata_record(
    *,
    status: str,
    x_index: int,
    y_index: int,
    x_row: dict[str, str],
    y_value: str,
    positive_prompt: str,
    prompt_hash: str,
    seed: int,
    generation_params: dict[str, object | None],
    workflow_hash: str,
    attempt: int,
) -> dict[str, object]:
    return {
        "status": status,
        "x_index": x_index,
        "y_index": y_index,
        "x_fields": {
            "gender": x_row.get("gender", ""),
            "characters": x_row.get("characters", ""),
            "series": x_row.get("series", ""),
            "rating": x_row.get("rating", ""),
            "general": x_row.get("general", ""),
            "quality": x_row.get("quality", ""),
        },
        "x_info_type": _extract_x_info_type(x_row),
        "y_value": y_value,
        "positive_prompt": positive_prompt,
        "prompt_hash": prompt_hash,
        "seed": seed,
        "attempt": attempt,
        "generation_params": generation_params,
        "workflow_hash": workflow_hash,
        "comfyui_prompt_id": None,
        "remote_images": None,
        "local_image_path": None,
        "local_image_paths": None,
        "error": None,
    }


def _collect_remote_images(history_item: dict[str, object]) -> list[dict[str, str]]:
    return _coordinator_collect_remote_images(history_item)


def _infer_image_extension(image: dict[str, str]) -> str:
    return _coordinator_infer_image_extension(image)


def _worker_submit_and_wait(
    args: argparse.Namespace,
    workflow_context: WorkflowContext,
    plan: _CellPlan,
) -> _GenOutcome:
    return _coordinator_worker_submit_and_wait(
        args,
        workflow_context,
        plan,
        patch_workflow,
        WorkflowOverrides,
        _final_negative_prompt_for_x_row,
        comfy_submit_prompt,
        comfy_wait_prompt_done_with_fallback,
        _build_base_metadata_record,
        _now_iso,
    )


def _worker_fetch_and_download(
    args: argparse.Namespace,
    run_dir: Path,
    req: _DownloadRequest,
) -> dict[str, object]:
    return _coordinator_worker_fetch_and_download(
        args,
        run_dir,
        req,
        comfy_get_history_item,
        comfy_download_image_to_path,
        _build_base_metadata_record,
        _now_iso,
    )


def _fetch_remote_images_with_retry(
    *,
    base_url: str,
    prompt_id: str,
    request_timeout_s: float,
    job_timeout_s: float,
) -> list[dict[str, str]]:
    return _coordinator_fetch_remote_images_with_retry(
        base_url=base_url,
        prompt_id=prompt_id,
        request_timeout_s=request_timeout_s,
        job_timeout_s=job_timeout_s,
        get_history_item=comfy_get_history_item,
    )


def _build_local_image_paths(
    *,
    x_index: int,
    y_index: int,
    remote_images: list[dict[str, str]],
) -> list[str]:
    return _coordinator_build_local_image_paths(
        x_index=x_index,
        y_index=y_index,
        remote_images=remote_images,
    )


def _serialize_error(exc: Exception) -> dict[str, object]:
    return _coordinator_serialize_error(exc)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _coerce_int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _coerce_float_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _coerce_str_or_none(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None


def _as_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    raise ValueError("workflow 结构不符合预期，请使用 CLIPTextEncode 版 workflow")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
