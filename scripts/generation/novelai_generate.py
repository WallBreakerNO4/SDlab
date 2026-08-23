# pyright: basic, reportPrivateUsage=false, reportUnusedCallResult=false, reportImplicitStringConcatenation=false

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import uuid
from pathlib import Path
from time import monotonic
from typing import Any, cast

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

if __package__ in {None, ""}:
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from scripts.generation.novelai_client import (
    NovelAIAPIClient,
    _build_error_payload,
    _normalize_model,
    _env_float,
    _env_int,
    novelai_worker,
)
from scripts.generation.prompt_grid import (
    compute_prompt_hash,
    derive_seed,
    read_x_descriptions,
    read_x_rows,
    read_y_rows_for_novelai,
)
from scripts.generation.runner_selection import (
    SelectedRow,
    _extract_x_info_type,
    _select_rows,
    _select_rows_by_fixed_indexes,
)
from scripts.generation.runner_prompt_template import (
    ALLOWED_TEMPLATE_KEYS,
    TEMPLATE_TOKEN_RE,
    _build_example_prompt as _prompt_build_example_prompt,
    _render_prompt_by_template as _prompt_render_prompt_by_template,
)
from scripts.generation.runner_records import (
    _build_base_metadata_record,
    _extract_local_image_path,
    _extract_local_image_paths,
    _next_attempt,
    _should_resume_skip,
)
from scripts.generation.retry_failed_selection import (
    _coerce_int_or_none,
    select_failed_and_incomplete_cells,
)
from scripts.generation.run_replay import load_run_replay_config
from scripts.generation.runner_retry import (
    _apply_replay_config_to_args,
    _build_retry_target_cells,
    _filter_retry_failed_cells,
    _parse_retry_error_codes,
    _validate_retry_failed_cells_consistency,
)
from scripts.generation.runner_payload import (
    _build_run_payload,
    _now_iso,
)
from scripts.generation.output_packager import (
    RunArtifacts,
    _MetadataWriter,
    _load_latest_metadata_records,
    _load_latest_metadata_records_strict,
    _metadata_writer,
    _prepare_existing_run_artifacts,
    _prepare_run_artifacts,
)
from scripts.generation.runner_coordinator import (
    RunStats,
    _CellPlan,
    _GenOutcome,
    _serialize_error,
    run_generation,
)
from scripts.generation.runner_config import (
    BACKEND_NOVELAI,
    load_runner_config,
)
from scripts.generation.runner_env import (
    _autoload_dotenv,
)
from scripts.run_naming import validate_run_key


DEFAULT_CONCURRENCY = 2
DEFAULT_JOB_TIMEOUT_S = 900.0
LOG = logging.getLogger(__name__)

ALLOWED_TEMPLATE_KEYS = ALLOWED_TEMPLATE_KEYS
TEMPLATE_TOKEN_RE = TEMPLATE_TOKEN_RE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="遍历 X/Y prompts 网格，调用 NovelAI API 生图并落盘 metadata。"
    )

    parser.add_argument(
        "--config",
        help="Runner YAML 配置文件路径 (image-run-config/v2, backend=novelai)。"
        "retry 模式从 run.json 回放，可省略。",
    )
    parser.add_argument("--run-dir")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--retry-failed", action="store_true", default=False)
    parser.add_argument("--retry-incomplete", action="store_true", default=False)
    parser.add_argument("--retry-error-code", default=None)

    parser.add_argument(
        "--concurrency",
        type=int,
        default=_env_int("NOVELAI_CONCURRENCY", DEFAULT_CONCURRENCY),
    )
    parser.add_argument(
        "--client-id",
        default=None,
    )

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
        _validate_args(args)
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


def _validate_args(args: argparse.Namespace) -> None:
    retry_mode = _is_retry_mode(args)

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
    elif not args.config:
        raise ValueError("fresh-run 模式必须提供 --config")

    if not args.client_id:
        args.client_id = str(uuid.uuid4())


def run(args: argparse.Namespace) -> int:
    _configure_logging()

    config = load_runner_config(args.config, repo_root=Path.cwd())
    if config.backend != BACKEND_NOVELAI:
        raise ValueError(
            f"配置 backend 必须为 {BACKEND_NOVELAI}，当前为 {config.backend}"
        )

    _apply_config_to_args(args, config)
    model_name = _normalize_model(config.model.key)
    novelai_fingerprint = _novelai_generation_fingerprint(args, model=model_name)

    x_rows = read_x_rows(args.x_json)
    y_rows = read_y_rows_for_novelai(args.y_json)
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

    run_payload = _build_run_payload(
        args=args,
        run_dir=run_artifacts.run_dir,
        x_selected=x_selected,
        y_selected=y_selected,
        workflow_context=None,
    )
    _apply_novelai_fingerprint_to_run_payload(
        run_payload,
        fingerprint=novelai_fingerprint,
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
    example_prompt = _build_example_prompt(
        args.template,
        x_selected,
        y_selected,
        quality_prompt=getattr(args, "quality_prompt", None),
    )
    if args.dry_run:
        print(f"组合总数: {total_cells}")
        print(f"示例正向提示词: {example_prompt}")

    latest_records = _load_latest_metadata_records(run_artifacts.metadata_path)

    stats = RunStats()

    LOG.info(
        "开始 NovelAI 运行: total_cells=%s dry_run=%s run_dir=%s",
        total_cells,
        args.dry_run,
        run_artifacts.run_dir,
    )

    client = NovelAIAPIClient(api_key="dry-run" if args.dry_run else None)
    if not args.dry_run:
        if client._api_key is None:
            print("错误: 未设置 NOVELAI_API_KEY 环境变量", file=sys.stderr)
            return 2
        # Anlas 守卫启动预检：非 Opus key 直接中止，并记录运行前余额基线。
        try:
            client.preflight()
        except Exception as exc:
            print(f"Anlas 守卫预检失败: {exc}", file=sys.stderr)
            return 2

    worker_fn = novelai_worker(client=client, model=model_name)

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
                    workflow_context=None,
                    workflow_hash=novelai_fingerprint,
                    stats=stats,
                    pbar=pbar,
                    writer=writer,
                    render_prompt=lambda template, x_row, y_value: (
                        _prompt_render_prompt_by_template(
                            template,
                            x_row,
                            y_value,
                            default_template="{quality}{rating}{y}{gender}{characters}{series}{general}",
                            quality_prompt=getattr(args, "quality_prompt", None),
                        )
                    ),
                    compute_prompt_hash=compute_prompt_hash,
                    derive_seed=derive_seed,
                    effective_generation_params=_novelai_effective_params,
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
                    patch_workflow=lambda *args, **kwargs: None,
                    workflow_overrides_factory=lambda **kwargs: None,
                    final_negative_prompt_for_x_row=_novelai_final_negative,
                    submit_prompt=lambda *args, **kwargs: "",
                    wait_prompt_done_with_fallback=lambda *args, **kwargs: None,
                    get_history_item=lambda *args, **kwargs: {},
                    download_image_to_path=lambda *args, **kwargs: Path("."),
                    worker_fn=worker_fn,
                )

    print(
        "结果统计: "
        f"success={stats.success}, skipped={stats.skipped}, "
        f"failed={stats.failed}, resume_hit={stats.resume_hit}"
    )

    return 1 if has_failed else 0


def run_retry(args: argparse.Namespace) -> int:
    _configure_logging()

    run_artifacts = _prepare_existing_run_artifacts(args.run_dir)
    run_artifacts.images_dir.mkdir(parents=True, exist_ok=True)

    # 目标 run 必须由 NovelAI 后端产出；模型 key 从 run.json 快照恢复并过白名单。
    model_name = _load_novelai_retry_model_key(run_artifacts.run_json_path)

    replay = load_run_replay_config(run_artifacts.run_dir, strict_sha256=True)
    _apply_replay_config_to_args(args, replay)
    novelai_fingerprint = _novelai_generation_fingerprint(args, model=model_name)

    x_rows = read_x_rows(args.x_json)
    y_rows = read_y_rows_for_novelai(args.y_json)
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

    # strict 一致性：失败格的 prompt hash / seed / fingerprint 与当前回放输入
    # 不一致时直接拒绝，防止恢复运行产出与原 run 不一致的结果。
    _validate_retry_failed_cells_consistency(
        target_cells=target_cells,
        latest_records=latest_records,
        x_rows_by_index={item.index: item.value for item in x_selected},
        y_rows_by_index={item.index: item.value for item in y_selected},
        template=args.template,
        base_seed=args.base_seed,
        workflow_hash=novelai_fingerprint,
        render_prompt=lambda template, x_row, y_value: (
            _prompt_render_prompt_by_template(
                template,
                x_row,
                y_value,
                default_template="{quality}{rating}{y}{gender}{characters}{series}{general}",
                quality_prompt=getattr(args, "quality_prompt", None),
            )
        ),
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

    client = NovelAIAPIClient(api_key="dry-run" if args.dry_run else None)
    if not args.dry_run:
        if client._api_key is None:
            print("错误: 未设置 NOVELAI_API_KEY 环境变量", file=sys.stderr)
            return 2
        # Anlas 守卫启动预检：非 Opus key 直接中止，并记录运行前余额基线。
        try:
            client.preflight()
        except Exception as exc:
            print(f"Anlas 守卫预检失败: {exc}", file=sys.stderr)
            return 2

    worker_fn = novelai_worker(client=client, model=model_name)

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
                    workflow_context=None,
                    workflow_hash=novelai_fingerprint,
                    stats=stats,
                    pbar=pbar,
                    writer=writer,
                    render_prompt=lambda template, x_row, y_value: (
                        _prompt_render_prompt_by_template(
                            template,
                            x_row,
                            y_value,
                            default_template="{quality}{rating}{y}{gender}{characters}{series}{general}",
                            quality_prompt=getattr(args, "quality_prompt", None),
                        )
                    ),
                    compute_prompt_hash=compute_prompt_hash,
                    derive_seed=derive_seed,
                    effective_generation_params=_novelai_effective_params,
                    next_attempt=lambda prev, increment: _next_attempt(
                        prev,
                        increment=increment,
                    ),
                    # retry 模式目标 cell 已经过筛选与一致性校验，不再做断点续跑跳过。
                    should_resume_skip=lambda existing, expected_prompt_hash, expected_seed, expected_workflow_hash: (
                        False
                    ),
                    build_base_metadata_record=_build_base_metadata_record,
                    extract_local_image_path=_extract_local_image_path,
                    extract_local_image_paths=_extract_local_image_paths,
                    now_iso=_now_iso,
                    patch_workflow=lambda *args, **kwargs: None,
                    workflow_overrides_factory=lambda **kwargs: None,
                    final_negative_prompt_for_x_row=_novelai_final_negative,
                    submit_prompt=lambda *args, **kwargs: "",
                    wait_prompt_done_with_fallback=lambda *args, **kwargs: None,
                    get_history_item=lambda *args, **kwargs: {},
                    download_image_to_path=lambda *args, **kwargs: Path("."),
                    cell_pairs=cell_pairs,
                    worker_fn=worker_fn,
                )

    print(
        "结果统计: "
        f"success={stats.success}, skipped={stats.skipped}, "
        f"failed={stats.failed}, resume_hit={stats.resume_hit}"
    )

    return 1 if has_failed else 0


def _load_novelai_retry_model_key(run_json_path: Path) -> str:
    """从 run.json 提取模型 key 并校验该 run 由 NovelAI 后端产出。

    retry 不读 --config：生成输入以 run.json 快照 + sha256 校验为准，
    模型 key 也必须来自原 run，保证 fingerprint 与原记录一致。
    """
    if not run_json_path.exists():
        raise ValueError(f"run.json 不存在: {run_json_path}")

    try:
        raw = run_json_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"run.json 读取失败: {run_json_path}") from exc

    try:
        payload = cast(object, json.loads(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"run.json 不是合法 JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("run.json 顶层必须为对象")

    backend = payload.get("backend", "comfyui")
    if backend != BACKEND_NOVELAI:
        raise ValueError(
            f"retry 目标 run 不是 NovelAI 运行（backend={backend}），"
            "请改用对应后端的 retry 入口"
        )

    model_obj = payload.get("model")
    if not isinstance(model_obj, dict):
        raise ValueError("run.json 缺少 model 快照，无法恢复 NovelAI run")
    model_key = model_obj.get("key")
    if not isinstance(model_key, str) or not model_key.strip():
        raise ValueError("run.json 的 model.key 缺失或为空，无法恢复 NovelAI run")

    return _normalize_model(model_key)


def _apply_config_to_args(args: argparse.Namespace, config: Any) -> None:
    args.config_schema_version = config.schema_version
    args.config_backend = config.backend
    args.config_path = config.config_path
    args.config_sha256 = config.config_sha256
    args.config_model = config.model
    args.run_key = config.model.key
    args.config_prompts = config.prompts
    args.config_workflow = config.workflow
    args.config_generation = config.generation
    args.config_selection = config.selection
    args.run_assets = config.assets

    args.x_json = config.prompts.x.path
    args.y_json = config.prompts.y.path
    args.template = config.generation.template
    args.quality_prompt = config.generation.quality_prompt
    args.base_seed = config.generation.base_seed
    args.workflow_json = config.workflow.path
    args.workflow_download_json = (
        config.workflow.download.path if config.workflow.download is not None else None
    )
    args.ksampler_node_id = config.workflow.ksampler_node_id

    args.negative_prompt = config.generation.negative_prompt
    args.append_negative_prompt = config.generation.append_negative_prompt
    args.width = config.generation.width or 832
    args.height = config.generation.height or 1216
    args.batch_size = config.generation.batch_size or 1
    args.steps = config.generation.steps or 28
    args.cfg = config.generation.cfg or 5.0
    args.denoise = config.generation.denoise
    args.sampler_name = config.generation.sampler_name
    args.scheduler = config.generation.scheduler

    args.base_url = ""
    args.request_timeout_s = 30.0
    args.job_timeout_s = DEFAULT_JOB_TIMEOUT_S

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


def _build_example_prompt(
    template: str,
    x_selected: list[SelectedRow],
    y_selected: list[SelectedRow],
    *,
    quality_prompt: str | None,
) -> str:
    return _prompt_build_example_prompt(
        template,
        x_selected,
        y_selected,
        render_prompt_by_template=lambda current_template, x_row, y_value: (
            _prompt_render_prompt_by_template(
                current_template,
                x_row,
                y_value,
                default_template="{quality}{rating}{y}{gender}{characters}{series}{general}",
                quality_prompt=quality_prompt,
            )
        ),
    )


def _novelai_effective_params(
    args: argparse.Namespace,
    workflow_context: Any,
    x_row: dict[str, str],
    seed: int,
) -> dict[str, object | None]:
    negative_prompt = _novelai_final_negative(args, workflow_context, x_row)
    return {
        "seed": seed,
        "negative_prompt": negative_prompt,
        "width": args.width,
        "height": args.height,
        "batch_size": args.batch_size,
        "steps": args.steps,
        "cfg": args.cfg,
        "denoise": args.denoise,
        "sampler_name": args.sampler_name,
        "scheduler": args.scheduler,
    }


def _novelai_generation_fingerprint(
    args: argparse.Namespace,
    *,
    model: str,
) -> str:
    payload = {
        "schema": "novelai-generation-fingerprint/v1",
        "backend": BACKEND_NOVELAI,
        "model": model,
        "quality": False,
        "uc_preset": "light",
        "generation": {
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
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _apply_novelai_fingerprint_to_run_payload(
    run_payload: dict[str, object],
    *,
    fingerprint: str,
) -> None:
    run_payload["workflow_api_sha256"] = fingerprint

    config_snapshot_obj = run_payload.get("config_snapshot")
    if not isinstance(config_snapshot_obj, dict):
        return
    workflow_obj = config_snapshot_obj.get("workflow")
    if not isinstance(workflow_obj, dict):
        return
    workflow_obj["api_sha256"] = fingerprint


def _novelai_final_negative(
    args: argparse.Namespace,
    workflow_context: Any,
    x_row: dict[str, str],
) -> str | None:
    base = args.negative_prompt
    append_val = (
        getattr(args, "append_negative_prompt", None)
        if _extract_x_info_type(x_row) == "normal"
        else None
    )

    _ = workflow_context

    if base is None:
        base = ""
    if append_val is None:
        append_val = ""

    base_stripped = base.strip()
    append_stripped = append_val.strip()

    if not base_stripped:
        return append_stripped if append_stripped else None

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


if __name__ == "__main__":
    raise SystemExit(main())
