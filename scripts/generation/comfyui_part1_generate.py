# pyright: basic, reportUnusedCallResult=false, reportImplicitStringConcatenation=false

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
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
)
from scripts.generation.retry_failed_selection import (  # noqa: E402
    select_failed_and_incomplete_cells,
)
from scripts.generation.run_replay import (  # noqa: E402
    load_run_replay_config,
)
from scripts.generation.runner_env import (  # noqa: E402
    _autoload_dotenv,
    _env_float,
    _env_optional_int,
    _env_str,
)
from scripts.generation.runner_selection import (  # noqa: E402
    SelectedRow,
    _parse_indexes,
    _select_rows,
    _select_rows_by_fixed_indexes,
)
from scripts.generation.runner_prompt_template import (  # noqa: E402
    ALLOWED_TEMPLATE_KEYS as _PROMPT_ALLOWED_TEMPLATE_KEYS,
    TEMPLATE_TOKEN_RE as _PROMPT_TEMPLATE_TOKEN_RE,
    _build_example_prompt as _prompt_build_example_prompt,
    _render_prompt_by_template as _prompt_render_prompt_by_template,
)
from scripts.generation.runner_workflow_context import (  # noqa: E402
    WorkflowContext as _RunnerWorkflowContext,
    _extract_ref_node_id as _workflow_extract_ref_node_id,
    _extract_workflow_defaults as _workflow_extract_workflow_defaults,
    _format_node_title as _workflow_format_node_title,
    _load_workflow_context as _workflow_load_workflow_context,
    _record_workflow_hash as _workflow_record_workflow_hash,
    _resolve_ksampler_id as _workflow_resolve_ksampler_id,
)
from scripts.generation.runner_records import (  # noqa: E402
    _build_base_metadata_record as _records_build_base_metadata_record,
    _effective_generation_params as _records_effective_generation_params,
    _effective_negative_prompt as _records_effective_negative_prompt,
    _extract_local_image_path as _records_extract_local_image_path,
    _extract_local_image_paths as _records_extract_local_image_paths,
    _final_negative_prompt_for_x_row as _records_final_negative_prompt_for_x_row,
    _next_attempt as _records_next_attempt,
    _should_resume_skip as _records_should_resume_skip,
)
from scripts.generation.runner_payload import (  # noqa: E402
    _build_run_payload as _payload_build_run_payload,
    _now_iso as _payload_now_iso,
    _sha256_file as _payload_sha256_file,
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
from scripts.generation.runner_config import load_runner_config  # noqa: E402
from scripts.run_naming import validate_run_key  # noqa: E402
from scripts.generation.workflow_patch import (  # noqa: E402
    WorkflowDict,
    WorkflowOverrides,
    patch_workflow,
)

DEFAULT_X_JSON = "data/prompts/X/common_prompts.yaml"
DEFAULT_Y_JSON = "data/prompts/Y/300_NAI_Styles_Table-test.yaml"
DEFAULT_TEMPLATE = "{gender}{characters}{series}{rating}{y}{general}{quality}"
DEFAULT_WORKFLOW_JSON = "data/comfyui-flow/api-json/CKNOOBRF.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8188"
DEFAULT_REQUEST_TIMEOUT_S = 30.0
DEFAULT_JOB_TIMEOUT_S = 600.0
LOG = logging.getLogger(__name__)

_DEPRECATED_BUSINESS_ENV_KEYS = (
    "COMFYUI_X_JSON",
    "COMFYUI_Y_JSON",
    "COMFYUI_TEMPLATE",
    "COMFYUI_BASE_SEED",
    "COMFYUI_WORKFLOW_JSON",
    "COMFYUI_KSAMPLER_NODE_ID",
    "COMFYUI_X_LIMIT",
    "COMFYUI_Y_LIMIT",
    "COMFYUI_X_INDEXES",
    "COMFYUI_Y_INDEXES",
    "COMFYUI_NEGATIVE_PROMPT",
    "COMFYUI_APPEND_NEGATIVE_PROMPT",
    "COMFYUI_WIDTH",
    "COMFYUI_HEIGHT",
    "COMFYUI_BATCH_SIZE",
    "COMFYUI_STEPS",
    "COMFYUI_CFG",
    "COMFYUI_DENOISE",
    "COMFYUI_SAMPLER_NAME",
    "COMFYUI_SCHEDULER",
)

ALLOWED_TEMPLATE_KEYS = _PROMPT_ALLOWED_TEMPLATE_KEYS
TEMPLATE_TOKEN_RE = _PROMPT_TEMPLATE_TOKEN_RE
WorkflowContext = _RunnerWorkflowContext


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="遍历 X/Y prompts 网格，调用 ComfyUI 生图并落盘 metadata。"
    )

    parser.add_argument(
        "--config",
        help="Runner YAML 配置文件路径。推荐将 per-run 配置放在 data/runs/ 目录下以便 Git 追踪。",
    )
    parser.add_argument("--run-dir")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--retry-incomplete",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--retry-error-code",
        default=None,
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
        default=_env_optional_int("COMFYUI_CONCURRENCY") or 8,
    )
    parser.add_argument("--client-id")

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
        _validate_runtime_args(args)
        if _is_retry_mode(args):
            return run_retry(args)
        _apply_fresh_run_config(args)
        return run(args)
    except ValueError as exc:
        print(f"参数错误: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"运行失败: {exc}", file=sys.stderr)
        return 2


def _is_retry_mode(args: argparse.Namespace) -> bool:
    return bool(args.retry_failed or args.retry_incomplete)


def _apply_fresh_run_config(args: argparse.Namespace) -> None:
    if not args.config:
        raise ValueError("fresh-run 模式必须提供 --config")

    deprecated_env = sorted(
        key
        for key in _DEPRECATED_BUSINESS_ENV_KEYS
        if os.getenv(key) is not None and (os.getenv(key) or "").strip() != ""
    )
    if deprecated_env:
        keys = ", ".join(deprecated_env)
        raise ValueError(f"使用 --config 时不允许设置已弃用业务环境变量: {keys}")

    config = load_runner_config(args.config, repo_root=Path.cwd())

    args.config_schema_version = config.schema_version
    args.config_path = config.config_path
    args.config_sha256 = config.config_sha256
    args.config_model = config.model
    args.run_key = config.model.key
    args.config_prompts = config.prompts
    args.config_workflow = config.workflow
    args.config_generation = config.generation
    args.config_selection = config.selection

    args.x_json = config.prompts.x.path
    args.y_json = config.prompts.y.path
    args.template = config.generation.template
    args.base_seed = config.generation.base_seed
    args.workflow_json = config.workflow.path
    args.workflow_download_json = (
        config.workflow.download.path if config.workflow.download is not None else None
    )
    args.ksampler_node_id = config.workflow.ksampler_node_id

    args.negative_prompt = config.generation.negative_prompt
    args.append_negative_prompt = config.generation.append_negative_prompt
    args.width = config.generation.width
    args.height = config.generation.height
    args.batch_size = config.generation.batch_size
    args.steps = config.generation.steps
    args.cfg = config.generation.cfg
    args.denoise = config.generation.denoise
    args.sampler_name = config.generation.sampler_name
    args.scheduler = config.generation.scheduler

    args.x_limit = config.selection.x_limit
    args.y_limit = config.selection.y_limit
    args.x_indexes = (
        ",".join(str(item) for item in config.selection.x_indexes)
        if config.selection.x_indexes is not None
        else None
    )
    args.y_indexes = (
        ",".join(str(item) for item in config.selection.y_indexes)
        if config.selection.y_indexes is not None
        else None
    )


def _validate_runtime_args(args: argparse.Namespace) -> None:
    retry_mode = _is_retry_mode(args)

    retry_error_codes = _parse_retry_error_codes(args.retry_error_code)
    if retry_error_codes is not None and not retry_mode:
        raise ValueError(
            "--retry-error-code 仅可与 --retry-failed/--retry-incomplete 一起使用"
        )


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

    run_artifacts = _prepare_run_artifacts(
        args.run_dir,
        default_run_key=_default_run_key(args),
    )
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
                    should_resume_skip=lambda existing, expected_prompt_hash, expected_seed, expected_workflow_hash: (
                        _should_resume_skip(
                            existing=existing,
                            run_dir=run_artifacts.run_dir,
                            expected_prompt_hash=expected_prompt_hash,
                            expected_seed=expected_seed,
                            expected_workflow_hash=expected_workflow_hash,
                        )
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
                    should_resume_skip=lambda existing, expected_prompt_hash, expected_seed, expected_workflow_hash: (
                        False
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
                    cell_pairs=cell_pairs,
                    save_image_prefix_builder=lambda run_id, x_index, y_index, seed, prompt_hash: (
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


def _default_run_key(args: argparse.Namespace) -> str:
    run_dir = getattr(args, "run_dir", None)
    if isinstance(run_dir, str) and run_dir.strip():
        return validate_run_key(Path(run_dir).name, field_name="run_dir")

    run_key = getattr(args, "run_key", None)
    if not isinstance(run_key, str):
        raise ValueError("fresh-run 缺少 model.key，无法生成默认 run 目录名")
    return validate_run_key(run_key, field_name="model.key")


def _validate_args(args: argparse.Namespace) -> None:
    retry_mode = _is_retry_mode(args)

    if args.request_timeout_s <= 0:
        raise ValueError("--request-timeout-s 必须 > 0")
    if args.job_timeout_s <= 0:
        raise ValueError("--job-timeout-s 必须 > 0")
    x_limit = getattr(args, "x_limit", None)
    if x_limit is not None and x_limit < 0:
        raise ValueError("--x-limit 不能小于 0")
    y_limit = getattr(args, "y_limit", None)
    if y_limit is not None and y_limit < 0:
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
        if not getattr(args, "workflow_json", None):
            raise ValueError("非 dry-run 模式必须提供 --workflow-json")

    if not args.client_id:
        args.client_id = str(uuid.uuid4())


def _append_negative_prompt(base: str | None, append: str | None) -> str:
    """纯函数：拼接 base negative prompt 和 append negative prompt。"""
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


_load_workflow_context = _workflow_load_workflow_context
_resolve_ksampler_id = _workflow_resolve_ksampler_id
_format_node_title = _workflow_format_node_title
_extract_workflow_defaults = _workflow_extract_workflow_defaults
_extract_ref_node_id = _workflow_extract_ref_node_id
_record_workflow_hash = _workflow_record_workflow_hash


def _build_run_payload(
    args: argparse.Namespace,
    run_dir: Path,
    x_selected: list[SelectedRow],
    y_selected: list[SelectedRow],
    workflow_context: WorkflowContext | None,
) -> dict[str, object]:
    return _payload_build_run_payload(
        args=args,
        run_dir=run_dir,
        x_selected=x_selected,
        y_selected=y_selected,
        workflow_context=workflow_context,
    )


def _build_example_prompt(
    template: str,
    x_selected: list[SelectedRow],
    y_selected: list[SelectedRow],
) -> str:
    return _prompt_build_example_prompt(
        template,
        x_selected,
        y_selected,
        render_prompt_by_template=_render_prompt_by_template,
    )


def _render_prompt_by_template(
    template: str,
    x_row: dict[str, str],
    y_value: str,
) -> str:
    return _prompt_render_prompt_by_template(
        template,
        x_row,
        y_value,
        default_template=DEFAULT_TEMPLATE,
    )


def _should_resume_skip(
    existing: dict[str, object] | None,
    run_dir: Path,
    expected_prompt_hash: str,
    expected_seed: int,
    expected_workflow_hash: str,
) -> bool:
    return _records_should_resume_skip(
        existing,
        run_dir,
        expected_prompt_hash,
        expected_seed,
        expected_workflow_hash,
    )


_extract_local_image_path = _records_extract_local_image_path
_extract_local_image_paths = _records_extract_local_image_paths
_effective_negative_prompt = _records_effective_negative_prompt


def _final_negative_prompt_for_x_row(
    args: argparse.Namespace,
    workflow_context: WorkflowContext | None,
    x_row: dict[str, str],
) -> str | None:
    return _records_final_negative_prompt_for_x_row(
        args,
        workflow_context,
        x_row,
        append_negative_prompt=_append_negative_prompt,
    )


def _effective_generation_params(
    args: argparse.Namespace,
    workflow_context: WorkflowContext | None,
    x_row: dict[str, str],
    seed: int,
) -> dict[str, object | None]:
    return _records_effective_generation_params(
        args,
        workflow_context,
        x_row,
        seed,
        final_negative_prompt_for_x_row=_final_negative_prompt_for_x_row,
    )


_next_attempt = _records_next_attempt


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
    return _records_build_base_metadata_record(
        status=status,
        x_index=x_index,
        y_index=y_index,
        x_row=x_row,
        y_value=y_value,
        positive_prompt=positive_prompt,
        prompt_hash=prompt_hash,
        seed=seed,
        generation_params=generation_params,
        workflow_hash=workflow_hash,
        attempt=attempt,
    )


_collect_remote_images = _coordinator_collect_remote_images
_infer_image_extension = _coordinator_infer_image_extension


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


_serialize_error = _coordinator_serialize_error
_sha256_file = _payload_sha256_file


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


_now_iso = _payload_now_iso


if __name__ == "__main__":
    raise SystemExit(main())
