# pyright: basic, reportUnusedCallResult=false, reportImplicitStringConcatenation=false

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import hashlib
import json
import logging
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from time import monotonic, sleep
from typing import cast

from dotenv import find_dotenv, load_dotenv
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
    X_INFO_TYPE_KEY,
    compute_prompt_hash,
    derive_seed,
    read_x_descriptions,
    read_x_rows,
    read_y_rows,
    render_positive_prompt,
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
DEFAULT_RUN_ROOT = "comfyui_api_outputs"

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
class SelectedRow:
    index: int
    value: dict[str, str]


@dataclass(slots=True)
class WorkflowContext:
    workflow: WorkflowDict
    workflow_json_path: str
    workflow_hash: str
    selected_ksampler_id: str
    default_negative_prompt: str
    default_params: dict[str, object | None]


@dataclass(slots=True)
class RunArtifacts:
    run_dir: Path
    images_dir: Path
    run_json_path: Path
    metadata_path: Path


@dataclass(slots=True)
class RunStats:
    success: int = 0
    skipped: int = 0
    failed: int = 0
    resume_hit: int = 0


@dataclass(slots=True)
class _CellPlan:
    x_index: int
    y_index: int
    x_row: dict[str, str]
    y_value: str
    positive_prompt: str
    prompt_hash: str
    seed: int
    generation_params: dict[str, object | None]
    workflow_hash: str
    save_image_prefix: str
    x_description: dict[str, str]


def _extract_x_info_type(x_row: dict[str, str]) -> str | None:
    value = x_row.get(X_INFO_TYPE_KEY)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


@dataclass(slots=True)
class _DownloadRequest:
    plan: _CellPlan
    prompt_id: str
    started_at: str
    started_mono: float


@dataclass(slots=True)
class _GenOutcome:
    record: dict[str, object] | None
    download: _DownloadRequest | None


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
        return run(args)
    except ValueError as exc:
        print(f"参数错误: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"运行失败: {exc}", file=sys.stderr)
        return 2


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
    has_failed = False

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
                if not args.dry_run and workflow_context is None:
                    raise ValueError("非 dry-run 模式必须提供可用 workflow")

                cell_iter = product(x_selected, y_selected)
                exhausted = False

                gen_futures: set[Future] = set()
                dl_futures: set[Future] = set()

                def _write_record(record: dict[str, object]) -> None:
                    nonlocal has_failed
                    writer.append(record)

                    x_index_obj = record.get("x_index")
                    y_index_obj = record.get("y_index")
                    if isinstance(x_index_obj, int) and isinstance(y_index_obj, int):
                        latest_records[(x_index_obj, y_index_obj)] = record

                    status = record.get("status")
                    if status == "success":
                        stats.success += 1
                    elif status == "failed":
                        stats.failed += 1
                        has_failed = True
                    elif status == "skipped":
                        stats.skipped += 1
                        if record.get("skip_reason") == "resume_hit":
                            stats.resume_hit += 1

                    pbar.set_postfix(
                        success=stats.success,
                        skipped=stats.skipped,
                        failed=stats.failed,
                        resume_hit=stats.resume_hit,
                        refresh=False,
                    )
                    pbar.update(1)

                def _get_x_description(x_index: int) -> dict[str, str]:
                    if x_index < len(x_descriptions):
                        return x_descriptions[x_index]
                    return {"zh": "", "en": ""}

                def _schedule_until_full(gen_pool: ThreadPoolExecutor) -> None:
                    nonlocal exhausted
                    while not exhausted and len(gen_futures) < args.concurrency:
                        try:
                            x_item, y_item = next(cell_iter)
                        except StopIteration:
                            exhausted = True
                            return

                        x_index = x_item.index
                        y_index = y_item.index
                        x_row = x_item.value
                        y_value = y_item.value.get("y", "")

                        positive_prompt = _render_prompt_by_template(
                            args.template, x_row, y_value
                        )
                        prompt_hash = compute_prompt_hash(positive_prompt)
                        seed = derive_seed(args.base_seed, x_index, y_index)

                        resume_record = latest_records.get((x_index, y_index))
                        if _should_resume_skip(
                            existing=resume_record,
                            run_dir=run_artifacts.run_dir,
                            expected_prompt_hash=prompt_hash,
                            expected_seed=seed,
                            expected_workflow_hash=workflow_hash,
                        ):
                            record = _build_base_metadata_record(
                                status="skipped",
                                x_index=x_index,
                                y_index=y_index,
                                x_row=x_row,
                                y_value=y_value,
                                positive_prompt=positive_prompt,
                                prompt_hash=prompt_hash,
                                seed=seed,
                                generation_params=_effective_generation_params(
                                    args,
                                    workflow_context,
                                    x_row,
                                    seed,
                                ),
                                workflow_hash=workflow_hash,
                            )
                            record["skip_reason"] = "resume_hit"
                            record["x_description"] = _get_x_description(x_index)
                            record["local_image_path"] = _extract_local_image_path(
                                resume_record
                            )
                            record["local_image_paths"] = _extract_local_image_paths(
                                resume_record
                            ) or (
                                [record["local_image_path"]]
                                if record.get("local_image_path")
                                else None
                            )
                            _write_record(record)
                            continue

                        if args.dry_run:
                            record = _build_base_metadata_record(
                                status="skipped",
                                x_index=x_index,
                                y_index=y_index,
                                x_row=x_row,
                                y_value=y_value,
                                positive_prompt=positive_prompt,
                                prompt_hash=prompt_hash,
                                seed=seed,
                                generation_params=_effective_generation_params(
                                    args,
                                    workflow_context,
                                    x_row,
                                    seed,
                                ),
                                workflow_hash=workflow_hash,
                            )
                            record["skip_reason"] = "dry_run"
                            record["x_description"] = _get_x_description(x_index)
                            _write_record(record)
                            continue

                        save_image_prefix = (
                            f"{run_id}/x{x_index}-y{y_index}-s{seed}-{prompt_hash[:8]}"
                        )
                        x_desc = _get_x_description(x_index)
                        plan = _CellPlan(
                            x_index=x_index,
                            y_index=y_index,
                            x_row=x_row,
                            y_value=y_value,
                            positive_prompt=positive_prompt,
                            prompt_hash=prompt_hash,
                            seed=seed,
                            generation_params=_effective_generation_params(
                                args,
                                workflow_context,
                                x_row,
                                seed,
                            ),
                            workflow_hash=workflow_hash,
                            save_image_prefix=save_image_prefix,
                            x_description=x_desc,
                        )

                        future = gen_pool.submit(
                            _worker_submit_and_wait,
                            args,
                            cast(WorkflowContext, workflow_context),
                            plan,
                        )
                        gen_futures.add(future)

                with ThreadPoolExecutor(max_workers=args.concurrency) as gen_pool:
                    with ThreadPoolExecutor(max_workers=args.concurrency) as dl_pool:
                        while True:
                            _schedule_until_full(gen_pool)

                            if exhausted and not gen_futures and not dl_futures:
                                break

                            if not gen_futures and not dl_futures:
                                continue

                            done, _ = wait(
                                gen_futures | dl_futures,
                                return_when=FIRST_COMPLETED,
                            )

                            for fut in done:
                                if fut in gen_futures:
                                    gen_futures.remove(fut)
                                    outcome = cast(_GenOutcome, fut.result())
                                    if outcome.record is not None:
                                        _write_record(outcome.record)
                                        continue
                                    if outcome.download is not None:
                                        dl_future = dl_pool.submit(
                                            _worker_fetch_and_download,
                                            args,
                                            run_artifacts.run_dir,
                                            outcome.download,
                                        )
                                        dl_futures.add(dl_future)
                                        continue
                                    raise RuntimeError(
                                        "internal error: gen outcome missing record and download"
                                    )

                                if fut in dl_futures:
                                    dl_futures.remove(fut)
                                    record = cast(dict[str, object], fut.result())
                                    _write_record(record)
                                    continue

                                raise RuntimeError("internal error: future not tracked")

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

    if not args.dry_run:
        if not args.workflow_json:
            raise ValueError("非 dry-run 模式必须提供 --workflow-json")

    if not args.client_id:
        args.client_id = str(uuid.uuid4())


def _prepare_run_artifacts(run_dir_arg: str | None) -> RunArtifacts:
    if run_dir_arg:
        run_dir = Path(run_dir_arg)
    else:
        run_root = Path(_env_str("COMFYUI_OUT_DIR") or DEFAULT_RUN_ROOT)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = run_root / f"run-{timestamp}"

    run_dir.mkdir(parents=True, exist_ok=True)
    return RunArtifacts(
        run_dir=run_dir,
        images_dir=run_dir / "images",
        run_json_path=run_dir / "run.json",
        metadata_path=run_dir / "metadata.jsonl",
    )


def _autoload_dotenv() -> None:
    dotenv_path = find_dotenv(filename=".env", usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path=dotenv_path, encoding="utf-8")
        return
    return


def _env_str(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _env_float(name: str, default: float) -> float:
    raw = _env_str(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 不是有效浮点数: {raw}") from exc


def _env_optional_float(name: str) -> float | None:
    raw = _env_str(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 不是有效浮点数: {raw}") from exc


def _env_optional_int(name: str) -> int | None:
    raw = _env_str(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 不是有效整数: {raw}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = _env_str(name)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(
        f"环境变量 {name} 不是有效布尔值: {raw} (可用: 1/0 true/false yes/no on/off)"
    )


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


def _resolve_append_negative_prompt(raw: str | None) -> str | None:
    """纯解析器：根据原始环境变量值解析追加负面提示词。

    Args:
        raw: 从 os.getenv 获取的原始值

    Returns:
        - None: 表示禁用追加（raw 存在但为空字符串）
        - str: 追加的负面提示词（raw 为 None 时返回默认值）
    """
    DEFAULT_APPEND = "nsfw, nipples, pussy, nude,"

    if raw is None:
        return DEFAULT_APPEND

    stripped = raw.strip()
    if not stripped:
        return None

    return stripped


def _env_append_negative_prompt() -> str | None:
    """读取 COMFYUI_APPEND_NEGATIVE_PROMPT 环境变量并解析。

    Returns:
        - None: 表示禁用追加（环境变量存在但为空）
        - str: 追加的负面提示词（环境变量缺失时返回默认值）
    """
    raw = os.getenv("COMFYUI_APPEND_NEGATIVE_PROMPT")
    return _resolve_append_negative_prompt(raw)


def _select_rows(
    rows: list[dict[str, str]],
    limit: int | None,
    indexes_raw: str | None,
    axis_name: str,
) -> list[SelectedRow]:
    indexed_rows = [
        SelectedRow(index=index, value=value) for index, value in enumerate(rows)
    ]

    indexes = _parse_indexes(indexes_raw, axis_name)
    if indexes is not None:
        selected: list[SelectedRow] = []
        for index in indexes:
            if index < 0 or index >= len(rows):
                raise ValueError(
                    f"--{axis_name}-indexes 包含越界索引: {index} (最大 {len(rows) - 1})"
                )
            selected.append(SelectedRow(index=index, value=rows[index]))
        indexed_rows = selected

    if limit is not None:
        indexed_rows = indexed_rows[:limit]

    return indexed_rows


def _parse_indexes(raw: str | None, axis_name: str) -> list[int] | None:
    if raw is None:
        return None

    tokens = [token.strip() for token in raw.split(",") if token.strip()]
    if not tokens:
        return []

    parsed: list[int] = []
    for token in tokens:
        if not token.isdigit():
            raise ValueError(f"--{axis_name}-indexes 仅支持非负整数列表: {raw}")
        parsed.append(int(token))

    unique: list[int] = []
    seen: set[int] = set()
    for value in parsed:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


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


def _load_latest_metadata_records(
    metadata_path: Path,
) -> dict[tuple[int, int], dict[str, object]]:
    latest: dict[tuple[int, int], dict[str, object]] = {}
    if not metadata_path.exists():
        return latest

    with metadata_path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue

            x_index = _coerce_int_or_none(payload.get("x_index"))
            y_index = _coerce_int_or_none(payload.get("y_index"))
            if x_index is None or y_index is None:
                continue

            latest[(x_index, y_index)] = payload

    return latest


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


class _MetadataWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.file = None

    def __enter__(self) -> "_MetadataWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_newline_terminated(self.path)
        self.file = self.path.open("a", encoding="utf-8")
        return self

    def append(self, record: dict[str, object]) -> None:
        if self.file is None:
            raise RuntimeError("metadata writer is closed")
        line = json.dumps(record, ensure_ascii=False)
        self.file.write(line)
        self.file.write("\n")
        self.file.flush()
        os.fsync(self.file.fileno())

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.file is not None:
            self.file.close()
            self.file = None


def _metadata_writer(path: Path) -> _MetadataWriter:
    return _MetadataWriter(path)


def _ensure_newline_terminated(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return

    with path.open("rb+") as file:
        file.seek(-1, os.SEEK_END)
        last_byte = file.read(1)
        if last_byte == b"\n":
            return
        file.seek(0, os.SEEK_END)
        file.write(b"\n")
        file.flush()
        os.fsync(file.fileno())


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
        "generation_params": generation_params,
        "workflow_hash": workflow_hash,
        "comfyui_prompt_id": None,
        "remote_images": None,
        "local_image_path": None,
        "local_image_paths": None,
        "error": None,
    }


def _collect_remote_images(history_item: dict[str, object]) -> list[dict[str, str]]:
    outputs_obj = history_item.get("outputs")
    if not isinstance(outputs_obj, dict):
        return []

    images: list[dict[str, str]] = []
    for node_payload in outputs_obj.values():
        if not isinstance(node_payload, dict):
            continue
        node_images = node_payload.get("images")
        if not isinstance(node_images, list):
            continue
        for item in node_images:
            if not isinstance(item, dict):
                continue
            filename = item.get("filename")
            if not isinstance(filename, str) or not filename:
                continue

            image_payload: dict[str, str] = {"filename": filename}
            subfolder = item.get("subfolder")
            if isinstance(subfolder, str) and subfolder:
                image_payload["subfolder"] = subfolder
            image_type = item.get("type")
            if isinstance(image_type, str) and image_type:
                image_payload["type"] = image_type
            images.append(image_payload)

    return images


def _infer_image_extension(image: dict[str, str]) -> str:
    filename = image.get("filename", "")
    suffix = Path(filename).suffix.lower()
    if suffix:
        return suffix
    return ".png"


def _worker_submit_and_wait(
    args: argparse.Namespace,
    workflow_context: WorkflowContext,
    plan: _CellPlan,
) -> _GenOutcome:
    started_at = _now_iso()
    started_mono = monotonic()
    prompt_id: str | None = None

    try:
        negative_prompt = _final_negative_prompt_for_x_row(
            args,
            workflow_context,
            plan.x_row,
        )
        if negative_prompt is None:
            raise ValueError("无法确定负面提示词")
        workflow_overrides = WorkflowOverrides(
            seed=plan.seed,
            steps=args.steps,
            cfg=args.cfg,
            denoise=args.denoise,
            sampler_name=args.sampler_name,
            scheduler=args.scheduler,
            width=args.width,
            height=args.height,
            batch_size=args.batch_size,
        )
        patched_workflow = patch_workflow(
            workflow_context.workflow,
            positive_prompt=plan.positive_prompt,
            negative_prompt=negative_prompt,
            overrides=workflow_overrides,
            ksampler_node_id=workflow_context.selected_ksampler_id,
            save_image_prefix=plan.save_image_prefix,
        )

        client_id = f"{args.client_id}-{uuid.uuid4().hex[:8]}"
        prompt_id = comfy_submit_prompt(
            base_url=args.base_url,
            workflow=cast(dict[str, object], patched_workflow),
            client_id=client_id,
            request_timeout_s=args.request_timeout_s,
        )
        comfy_wait_prompt_done_with_fallback(
            base_url=args.base_url,
            client_id=client_id,
            prompt_id=prompt_id,
            request_timeout_s=args.request_timeout_s,
            job_timeout_s=args.job_timeout_s,
        )

        return _GenOutcome(
            record=None,
            download=_DownloadRequest(
                plan=plan,
                prompt_id=prompt_id,
                started_at=started_at,
                started_mono=started_mono,
            ),
        )
    except Exception as exc:
        LOG.exception("生成失败: x=%s y=%s", plan.x_index, plan.y_index)
        finished_at = _now_iso()
        elapsed_ms = int((monotonic() - started_mono) * 1000)
        record = _build_base_metadata_record(
            status="failed",
            x_index=plan.x_index,
            y_index=plan.y_index,
            x_row=plan.x_row,
            y_value=plan.y_value,
            positive_prompt=plan.positive_prompt,
            prompt_hash=plan.prompt_hash,
            seed=plan.seed,
            generation_params=plan.generation_params,
            workflow_hash=plan.workflow_hash,
        )
        record["x_description"] = plan.x_description
        record["comfyui_prompt_id"] = prompt_id
        record["started_at"] = started_at
        record["finished_at"] = finished_at
        record["elapsed_ms"] = elapsed_ms
        record["error"] = _serialize_error(exc)
        return _GenOutcome(record=record, download=None)


def _worker_fetch_and_download(
    args: argparse.Namespace,
    run_dir: Path,
    req: _DownloadRequest,
) -> dict[str, object]:
    plan = req.plan
    prompt_id = req.prompt_id
    remote_images: list[dict[str, str]] | None = None
    local_image_paths: list[str] | None = None

    try:
        remote_images = _fetch_remote_images_with_retry(
            base_url=args.base_url,
            prompt_id=prompt_id,
            request_timeout_s=args.request_timeout_s,
            job_timeout_s=args.job_timeout_s,
        )
        if not remote_images:
            raise ValueError("history 未返回可下载图像")

        local_image_paths = _build_local_image_paths(
            x_index=plan.x_index,
            y_index=plan.y_index,
            remote_images=remote_images,
        )
        for image, local_path in zip(remote_images, local_image_paths, strict=True):
            _ = comfy_download_image_to_path(
                base_url=args.base_url,
                image=cast(dict[str, object], image),
                output_path=run_dir / local_path,
                request_timeout_s=args.request_timeout_s,
            )

        finished_at = _now_iso()
        elapsed_ms = int((monotonic() - req.started_mono) * 1000)
        record = _build_base_metadata_record(
            status="success",
            x_index=plan.x_index,
            y_index=plan.y_index,
            x_row=plan.x_row,
            y_value=plan.y_value,
            positive_prompt=plan.positive_prompt,
            prompt_hash=plan.prompt_hash,
            seed=plan.seed,
            generation_params=plan.generation_params,
            workflow_hash=plan.workflow_hash,
        )
        record["x_description"] = plan.x_description
        record["comfyui_prompt_id"] = prompt_id
        record["remote_images"] = remote_images
        record["local_image_paths"] = local_image_paths
        record["local_image_path"] = local_image_paths[0] if local_image_paths else None
        record["started_at"] = req.started_at
        record["finished_at"] = finished_at
        record["elapsed_ms"] = elapsed_ms
        return record
    except Exception as exc:
        LOG.exception("下载失败: x=%s y=%s", plan.x_index, plan.y_index)
        finished_at = _now_iso()
        elapsed_ms = int((monotonic() - req.started_mono) * 1000)
        record = _build_base_metadata_record(
            status="failed",
            x_index=plan.x_index,
            y_index=plan.y_index,
            x_row=plan.x_row,
            y_value=plan.y_value,
            positive_prompt=plan.positive_prompt,
            prompt_hash=plan.prompt_hash,
            seed=plan.seed,
            generation_params=plan.generation_params,
            workflow_hash=plan.workflow_hash,
        )
        record["x_description"] = plan.x_description
        record["comfyui_prompt_id"] = prompt_id
        record["remote_images"] = remote_images
        record["local_image_paths"] = local_image_paths
        record["local_image_path"] = local_image_paths[0] if local_image_paths else None
        record["started_at"] = req.started_at
        record["finished_at"] = finished_at
        record["elapsed_ms"] = elapsed_ms
        record["error"] = _serialize_error(exc)
        return record


def _fetch_remote_images_with_retry(
    *,
    base_url: str,
    prompt_id: str,
    request_timeout_s: float,
    job_timeout_s: float,
) -> list[dict[str, str]]:
    deadline = monotonic() + min(10.0, max(1.0, job_timeout_s))
    while True:
        history_item = comfy_get_history_item(
            base_url=base_url,
            prompt_id=prompt_id,
            request_timeout_s=request_timeout_s,
        )
        images = _collect_remote_images(history_item)
        if images:
            return images

        if monotonic() >= deadline:
            return []
        sleep(0.25)


def _build_local_image_paths(
    *,
    x_index: int,
    y_index: int,
    remote_images: list[dict[str, str]],
) -> list[str]:
    paths: list[str] = []
    for i, image in enumerate(remote_images):
        ext = _infer_image_extension(image)
        if i == 0:
            paths.append(f"images/x{x_index}-y{y_index}{ext}")
        else:
            paths.append(f"images/x{x_index}-y{y_index}-{i}{ext}")
    return paths


def _serialize_error(exc: Exception) -> dict[str, object]:
    if isinstance(exc, ComfyUIClientError):
        return exc.as_metadata()
    return {
        "type": exc.__class__.__name__,
        "message": str(exc),
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
