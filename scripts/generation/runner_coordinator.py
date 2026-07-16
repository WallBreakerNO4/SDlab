from __future__ import annotations

import argparse
from collections.abc import Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from itertools import product
import logging
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Callable, cast
import uuid

from scripts.generation.prompt_grid import (
    Y_ARTIST_CHAIN,
    Y_COLLECTION_ID,
    Y_ITEM_INDEX,
    Y_POSITIVE_VALUE,
    Y_STYLE_KEY,
)


LOG = logging.getLogger(__name__)


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
    artist_chain: str | None = None
    y_common_prompt: str | None = None
    attempt: int = 1
    y_prompt_ref: dict[str, object] | None = None


@dataclass(slots=True)
class _DownloadRequest:
    plan: _CellPlan
    prompt_id: str
    started_at: str
    started_mono: float
    remote_images: list[dict[str, str]] | None = None
    recovery_mode: str | None = None


@dataclass(slots=True)
class _GenOutcome:
    record: dict[str, object] | None
    download: _DownloadRequest | None


class GenerationCoordinator:
    def __init__(
        self,
        *,
        args: argparse.Namespace,
        x_selected: list[Any],
        y_selected: list[Any],
        x_descriptions: list[dict[str, str]],
        latest_records: dict[tuple[int, int], dict[str, object]],
        run_dir: Path,
        run_id: str,
        workflow_context: Any,
        workflow_hash: str,
        stats: RunStats,
        pbar: Any,
        writer: Any,
        render_prompt: Callable[[str, dict[str, str], str], str],
        compute_prompt_hash: Callable[[str, str | None], str],
        derive_seed: Callable[[int, int, int], int],
        effective_generation_params: Callable[
            [argparse.Namespace, Any, dict[str, str], int],
            dict[str, object | None],
        ],
        next_attempt: Callable[[dict[str, object] | None, bool], int],
        should_resume_skip: Callable[[dict[str, object] | None, str, int, str], bool],
        build_base_metadata_record: Callable[..., dict[str, object]],
        extract_local_image_path: Callable[[dict[str, object] | None], str | None],
        extract_local_image_paths: Callable[
            [dict[str, object] | None], list[str] | None
        ],
        now_iso: Callable[[], str],
        patch_workflow: Callable[..., Any],
        workflow_overrides_factory: Callable[..., object],
        final_negative_prompt_for_x_row: Callable[
            [argparse.Namespace, Any, dict[str, str]], str | None
        ],
        submit_prompt: Callable[..., str],
        wait_prompt_done_with_fallback: Callable[..., None],
        get_history_item: Callable[..., dict[str, object]],
        download_image_to_path: Callable[..., Path],
        cell_pairs: Iterable[tuple[Any, Any]] | None = None,
        save_image_prefix_builder: (
            Callable[[str, int, int, int, str], str] | None
        ) = None,
        worker_fn: Callable[..., Any] | None = None,
    ):
        self.args = args
        self.x_descriptions = x_descriptions
        self.latest_records = latest_records
        self.run_dir = run_dir
        self.run_id = run_id
        self.workflow_context = workflow_context
        self.workflow_hash = workflow_hash
        self.stats = stats
        self.pbar = pbar
        self.writer = writer

        self.render_prompt = render_prompt
        self.compute_prompt_hash = compute_prompt_hash
        self.derive_seed = derive_seed
        self.effective_generation_params = effective_generation_params
        self.next_attempt = next_attempt
        self.should_resume_skip = should_resume_skip
        self.build_base_metadata_record = build_base_metadata_record
        self.extract_local_image_path = extract_local_image_path
        self.extract_local_image_paths = extract_local_image_paths
        self.now_iso = now_iso
        self.patch_workflow = patch_workflow
        self.workflow_overrides_factory = workflow_overrides_factory
        self.final_negative_prompt_for_x_row = final_negative_prompt_for_x_row

        self.submit_prompt = submit_prompt
        self.wait_prompt_done_with_fallback = wait_prompt_done_with_fallback
        self.get_history_item = get_history_item
        self.download_image_to_path = download_image_to_path
        self.worker_fn = worker_fn if worker_fn is not None else _worker_submit_and_wait

        if cell_pairs is None:
            self.cell_iter = product(x_selected, y_selected)
        else:
            self.cell_iter = iter(cell_pairs)
        self.save_image_prefix_builder = save_image_prefix_builder
        self.exhausted = False
        self.gen_futures: set[Future[Any]] = set()
        self.dl_futures: set[Future[Any]] = set()
        self.has_failed = False

    def run(self) -> bool:
        download_concurrency = _resolve_download_concurrency(self.args)
        max_pending_futures = self.args.concurrency + download_concurrency
        with ThreadPoolExecutor(max_workers=self.args.concurrency) as gen_pool:
            with ThreadPoolExecutor(max_workers=download_concurrency) as dl_pool:
                while True:
                    self._schedule_until_full(
                        gen_pool,
                        dl_pool,
                        max_pending_futures=max_pending_futures,
                    )

                    if self.exhausted and not self.gen_futures and not self.dl_futures:
                        break

                    if not self.gen_futures and not self.dl_futures:
                        continue

                    done, _ = wait(
                        self.gen_futures | self.dl_futures,
                        return_when=FIRST_COMPLETED,
                    )

                    for fut in done:
                        if fut in self.gen_futures:
                            self.gen_futures.remove(fut)
                            outcome = cast(_GenOutcome, fut.result())
                            if outcome.record is not None:
                                self._write_record(outcome.record)
                                continue
                            if outcome.download is not None:
                                dl_future = dl_pool.submit(
                                    _worker_fetch_and_download,
                                    self.args,
                                    self.run_dir,
                                    outcome.download,
                                    self.get_history_item,
                                    self.download_image_to_path,
                                    self.build_base_metadata_record,
                                    self.now_iso,
                                )
                                self.dl_futures.add(cast(Future[Any], dl_future))
                                continue
                            raise RuntimeError(
                                "internal error: gen outcome missing record and download"
                            )

                        if fut in self.dl_futures:
                            self.dl_futures.remove(fut)
                            record = cast(dict[str, object], fut.result())
                            self._write_record(record)
                            continue

                        raise RuntimeError("internal error: future not tracked")

        return self.has_failed

    def _schedule_until_full(
        self,
        gen_pool: ThreadPoolExecutor,
        dl_pool: ThreadPoolExecutor,
        *,
        max_pending_futures: int,
    ) -> None:
        while (
            not self.exhausted
            and len(self.gen_futures) < self.args.concurrency
            and len(self.gen_futures) + len(self.dl_futures) < max_pending_futures
        ):
            try:
                x_item, y_item = next(self.cell_iter)
            except StopIteration:
                self.exhausted = True
                return

            x_index = x_item.index
            y_index = y_item.index
            x_row = x_item.value
            y_value = y_item.value.get("y", "")
            positive_y_value = y_item.value.get(Y_POSITIVE_VALUE, y_value)
            artist_chain_obj = y_item.value.get(Y_ARTIST_CHAIN)
            artist_chain = (
                artist_chain_obj if isinstance(artist_chain_obj, str) else None
            )
            y_common_prompt = (
                positive_y_value
                if Y_POSITIVE_VALUE in y_item.value
                and isinstance(positive_y_value, str)
                else None
            )
            y_prompt_ref = _extract_y_prompt_ref(y_item)

            positive_prompt = self.render_prompt(
                self.args.template,
                x_row,
                positive_y_value,
            )
            prompt_hash = self.compute_prompt_hash(positive_prompt, artist_chain)
            seed = self.derive_seed(self.args.base_seed, x_index, y_index)

            resume_record = self.latest_records.get((x_index, y_index))
            skip_attempt = self.next_attempt(resume_record, False)
            if self.should_resume_skip(
                resume_record,
                prompt_hash,
                seed,
                self.workflow_hash,
            ):
                record = self.build_base_metadata_record(
                    status="skipped",
                    x_index=x_index,
                    y_index=y_index,
                    x_row=x_row,
                    y_value=y_value,
                    positive_prompt=positive_prompt,
                    prompt_hash=prompt_hash,
                    seed=seed,
                    generation_params=self.effective_generation_params(
                        self.args,
                        self.workflow_context,
                        x_row,
                        seed,
                    ),
                    workflow_hash=self.workflow_hash,
                    attempt=skip_attempt,
                )
                record["skip_reason"] = "resume_hit"
                _apply_mixer_prompt_parts(
                    record,
                    artist_chain=artist_chain,
                    y_common_prompt=y_common_prompt,
                )
                _apply_y_prompt_ref(record, y_prompt_ref)
                record["x_description"] = self._get_x_description(x_index)
                record["local_image_path"] = self.extract_local_image_path(
                    resume_record
                )
                record["local_image_paths"] = self.extract_local_image_paths(
                    resume_record
                ) or (
                    [record["local_image_path"]]
                    if record.get("local_image_path")
                    else None
                )
                self._write_record(record)
                continue

            if self.args.dry_run:
                record = self.build_base_metadata_record(
                    status="skipped",
                    x_index=x_index,
                    y_index=y_index,
                    x_row=x_row,
                    y_value=y_value,
                    positive_prompt=positive_prompt,
                    prompt_hash=prompt_hash,
                    seed=seed,
                    generation_params=self.effective_generation_params(
                        self.args,
                        self.workflow_context,
                        x_row,
                        seed,
                    ),
                    workflow_hash=self.workflow_hash,
                    attempt=skip_attempt,
                )
                record["skip_reason"] = "dry_run"
                _apply_mixer_prompt_parts(
                    record,
                    artist_chain=artist_chain,
                    y_common_prompt=y_common_prompt,
                )
                _apply_y_prompt_ref(record, y_prompt_ref)
                record["x_description"] = self._get_x_description(x_index)
                self._write_record(record)
                continue

            if self.save_image_prefix_builder is not None:
                save_image_prefix = self.save_image_prefix_builder(
                    self.run_id,
                    x_index,
                    y_index,
                    seed,
                    prompt_hash,
                )
            else:
                save_image_prefix = (
                    f"{self.run_id}/x{x_index}-y{y_index}-s{seed}-{prompt_hash[:8]}"
                )
            plan = _CellPlan(
                x_index=x_index,
                y_index=y_index,
                x_row=x_row,
                y_value=y_value,
                positive_prompt=positive_prompt,
                prompt_hash=prompt_hash,
                seed=seed,
                generation_params=self.effective_generation_params(
                    self.args,
                    self.workflow_context,
                    x_row,
                    seed,
                ),
                y_prompt_ref=y_prompt_ref,
                workflow_hash=self.workflow_hash,
                save_image_prefix=save_image_prefix,
                x_description=self._get_x_description(x_index),
                artist_chain=artist_chain,
                y_common_prompt=y_common_prompt,
                attempt=self.next_attempt(resume_record, True),
            )

            recovery_request = _build_download_recovery_request(
                resume_record,
                plan=plan,
                now_iso=self.now_iso,
            )
            if recovery_request is not None:
                future = dl_pool.submit(
                    _worker_fetch_and_download,
                    self.args,
                    self.run_dir,
                    recovery_request,
                    self.get_history_item,
                    self.download_image_to_path,
                    self.build_base_metadata_record,
                    self.now_iso,
                )
                self.dl_futures.add(cast(Future[Any], future))
                continue

            future = gen_pool.submit(
                self.worker_fn,
                self.args,
                self.run_dir,
                self.workflow_context,
                plan,
                self.patch_workflow,
                self.workflow_overrides_factory,
                self.final_negative_prompt_for_x_row,
                self.submit_prompt,
                self.wait_prompt_done_with_fallback,
                self.build_base_metadata_record,
                self.now_iso,
            )
            self.gen_futures.add(cast(Future[Any], future))

    def _get_x_description(self, x_index: int) -> dict[str, str]:
        if x_index < len(self.x_descriptions):
            return self.x_descriptions[x_index]
        return {"zh": "", "en": ""}

    def _write_record(self, record: dict[str, object]) -> None:
        self.writer.append(record)

        x_index_obj = record.get("x_index")
        y_index_obj = record.get("y_index")
        if isinstance(x_index_obj, int) and isinstance(y_index_obj, int):
            self.latest_records[(x_index_obj, y_index_obj)] = record

        status = record.get("status")
        if status == "success":
            self.stats.success += 1
        elif status == "failed":
            self.stats.failed += 1
            self.has_failed = True
        elif status == "skipped":
            self.stats.skipped += 1
            if record.get("skip_reason") == "resume_hit":
                self.stats.resume_hit += 1

        self.pbar.set_postfix(
            success=self.stats.success,
            skipped=self.stats.skipped,
            failed=self.stats.failed,
            resume_hit=self.stats.resume_hit,
            refresh=False,
        )
        self.pbar.update(1)


def run_generation(
    *,
    args: argparse.Namespace,
    x_selected: list[Any],
    y_selected: list[Any],
    x_descriptions: list[dict[str, str]],
    latest_records: dict[tuple[int, int], dict[str, object]],
    run_dir: Path,
    run_id: str,
    workflow_context: Any,
    workflow_hash: str,
    stats: RunStats,
    pbar: Any,
    writer: Any,
    render_prompt: Callable[[str, dict[str, str], str], str],
    compute_prompt_hash: Callable[[str, str | None], str],
    derive_seed: Callable[[int, int, int], int],
    effective_generation_params: Callable[
        [argparse.Namespace, Any, dict[str, str], int],
        dict[str, object | None],
    ],
    next_attempt: Callable[[dict[str, object] | None, bool], int],
    should_resume_skip: Callable[[dict[str, object] | None, str, int, str], bool],
    build_base_metadata_record: Callable[..., dict[str, object]],
    extract_local_image_path: Callable[[dict[str, object] | None], str | None],
    extract_local_image_paths: Callable[[dict[str, object] | None], list[str] | None],
    now_iso: Callable[[], str],
    patch_workflow: Callable[..., Any],
    workflow_overrides_factory: Callable[..., object],
    final_negative_prompt_for_x_row: Callable[
        [argparse.Namespace, Any, dict[str, str]], str | None
    ],
    submit_prompt: Callable[..., str],
    wait_prompt_done_with_fallback: Callable[..., None],
    get_history_item: Callable[..., dict[str, object]],
    download_image_to_path: Callable[..., Path],
    cell_pairs: Iterable[tuple[Any, Any]] | None = None,
    save_image_prefix_builder: (Callable[[str, int, int, int, str], str] | None) = None,
    worker_fn: Callable[..., Any] | None = None,
) -> bool:
    return GenerationCoordinator(
        args=args,
        x_selected=x_selected,
        y_selected=y_selected,
        x_descriptions=x_descriptions,
        latest_records=latest_records,
        run_dir=run_dir,
        run_id=run_id,
        workflow_context=workflow_context,
        workflow_hash=workflow_hash,
        stats=stats,
        pbar=pbar,
        writer=writer,
        render_prompt=render_prompt,
        compute_prompt_hash=compute_prompt_hash,
        derive_seed=derive_seed,
        effective_generation_params=effective_generation_params,
        next_attempt=next_attempt,
        should_resume_skip=should_resume_skip,
        build_base_metadata_record=build_base_metadata_record,
        extract_local_image_path=extract_local_image_path,
        extract_local_image_paths=extract_local_image_paths,
        now_iso=now_iso,
        patch_workflow=patch_workflow,
        workflow_overrides_factory=workflow_overrides_factory,
        final_negative_prompt_for_x_row=final_negative_prompt_for_x_row,
        submit_prompt=submit_prompt,
        wait_prompt_done_with_fallback=wait_prompt_done_with_fallback,
        get_history_item=get_history_item,
        download_image_to_path=download_image_to_path,
        cell_pairs=cell_pairs,
        save_image_prefix_builder=save_image_prefix_builder,
        worker_fn=worker_fn,
    ).run()


def _worker_submit_and_wait(
    args: argparse.Namespace,
    run_dir: Path,
    workflow_context: Any,
    plan: _CellPlan,
    patch_workflow: Callable[..., Any],
    workflow_overrides_factory: Callable[..., object],
    final_negative_prompt_for_x_row: Callable[
        [argparse.Namespace, Any, dict[str, str]], str | None
    ],
    submit_prompt: Callable[..., str],
    wait_prompt_done_with_fallback: Callable[..., None],
    build_base_metadata_record: Callable[..., dict[str, object]],
    now_iso: Callable[[], str],
) -> _GenOutcome:
    started_at = now_iso()
    started_mono = monotonic()
    prompt_id: str | None = None

    try:
        negative_prompt = final_negative_prompt_for_x_row(
            args, workflow_context, plan.x_row
        )
        if negative_prompt is None:
            raise ValueError("无法确定负面提示词")

        workflow_overrides = workflow_overrides_factory(
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
            artist_chain=plan.artist_chain,
        )

        client_id = f"{args.client_id}-{uuid.uuid4().hex[:8]}"
        prompt_id = submit_prompt(
            base_url=args.base_url,
            workflow=cast(dict[str, object], patched_workflow),
            client_id=client_id,
            request_timeout_s=args.request_timeout_s,
        )
        wait_prompt_done_with_fallback(
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
        finished_at = now_iso()
        elapsed_ms = int((monotonic() - started_mono) * 1000)
        record = build_base_metadata_record(
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
            attempt=plan.attempt,
        )
        record["x_description"] = plan.x_description
        _apply_mixer_prompt_parts(
            record,
            artist_chain=plan.artist_chain,
            y_common_prompt=plan.y_common_prompt,
        )
        _apply_y_prompt_ref(record, plan.y_prompt_ref)
        record["comfyui_prompt_id"] = prompt_id
        record["started_at"] = started_at
        record["finished_at"] = finished_at
        record["elapsed_ms"] = elapsed_ms
        record["failure_stage"] = "generation"
        record["error"] = _serialize_error(exc)
        return _GenOutcome(record=record, download=None)


def _worker_fetch_and_download(
    args: argparse.Namespace,
    run_dir: Path,
    req: _DownloadRequest,
    get_history_item: Callable[..., dict[str, object]],
    download_image_to_path: Callable[..., Path],
    build_base_metadata_record: Callable[..., dict[str, object]],
    now_iso: Callable[[], str],
) -> dict[str, object]:
    plan = req.plan
    prompt_id = req.prompt_id
    remote_images = req.remote_images
    local_image_paths: list[str] | None = None

    try:
        if remote_images is None:
            remote_images = _fetch_remote_images_with_retry(
                base_url=args.base_url,
                prompt_id=prompt_id,
                request_timeout_s=args.request_timeout_s,
                job_timeout_s=args.job_timeout_s,
                get_history_item=get_history_item,
            )
        if not remote_images:
            raise ValueError("history 未返回可下载图像")

        local_image_paths = _build_local_image_paths(
            x_index=plan.x_index,
            y_index=plan.y_index,
            remote_images=remote_images,
        )
        for image, local_path in zip(remote_images, local_image_paths, strict=True):
            output_path = run_dir / local_path
            if req.recovery_mode == "download_only" and output_path.is_file():
                continue
            _ = download_image_to_path(
                base_url=args.base_url,
                image=cast(dict[str, object], image),
                output_path=output_path,
                request_timeout_s=_resolve_download_read_timeout_s(args),
            )

        finished_at = now_iso()
        elapsed_ms = int((monotonic() - req.started_mono) * 1000)
        record = build_base_metadata_record(
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
            attempt=plan.attempt,
        )
        record["x_description"] = plan.x_description
        _apply_mixer_prompt_parts(
            record,
            artist_chain=plan.artist_chain,
            y_common_prompt=plan.y_common_prompt,
        )
        _apply_y_prompt_ref(record, plan.y_prompt_ref)
        record["comfyui_prompt_id"] = prompt_id
        record["remote_images"] = remote_images
        record["local_image_paths"] = local_image_paths
        record["local_image_path"] = local_image_paths[0] if local_image_paths else None
        record["started_at"] = req.started_at
        record["finished_at"] = finished_at
        record["elapsed_ms"] = elapsed_ms
        if req.recovery_mode is not None:
            record["recovery_mode"] = req.recovery_mode
        return record
    except Exception as exc:
        LOG.exception("下载失败: x=%s y=%s", plan.x_index, plan.y_index)
        finished_at = now_iso()
        elapsed_ms = int((monotonic() - req.started_mono) * 1000)
        record = build_base_metadata_record(
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
            attempt=plan.attempt,
        )
        record["x_description"] = plan.x_description
        _apply_mixer_prompt_parts(
            record,
            artist_chain=plan.artist_chain,
            y_common_prompt=plan.y_common_prompt,
        )
        _apply_y_prompt_ref(record, plan.y_prompt_ref)
        record["comfyui_prompt_id"] = prompt_id
        record["remote_images"] = remote_images
        record["local_image_paths"] = local_image_paths
        record["local_image_path"] = local_image_paths[0] if local_image_paths else None
        record["started_at"] = req.started_at
        record["finished_at"] = finished_at
        record["elapsed_ms"] = elapsed_ms
        record["failure_stage"] = "download"
        if req.recovery_mode is not None:
            record["recovery_mode"] = req.recovery_mode
        record["error"] = _serialize_error(exc)
        return record


def _resolve_download_concurrency(args: argparse.Namespace) -> int:
    value = getattr(args, "download_concurrency", None)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return min(args.concurrency, 4)


def _resolve_download_read_timeout_s(args: argparse.Namespace) -> float:
    value = getattr(args, "download_read_timeout_s", None)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    return float(args.request_timeout_s)


def _build_download_recovery_request(
    record: dict[str, object] | None,
    *,
    plan: _CellPlan,
    now_iso: Callable[[], str],
) -> _DownloadRequest | None:
    if record is None or record.get("status") not in {"failed", "success", "skipped"}:
        return None

    prompt_id_obj = record.get("comfyui_prompt_id")
    if not isinstance(prompt_id_obj, str) or not prompt_id_obj.strip():
        return None

    if (
        record.get("recovery_mode") == "download_only"
        and _record_error_status_code(record) == 404
    ):
        return None

    raw_remote_images = record.get("remote_images")
    remote_images = _coerce_persistent_remote_images(raw_remote_images)
    if remote_images is None:
        if raw_remote_images is not None or record.get("failure_stage") != "download":
            return None

    return _DownloadRequest(
        plan=plan,
        prompt_id=prompt_id_obj.strip(),
        started_at=now_iso(),
        started_mono=monotonic(),
        remote_images=remote_images,
        recovery_mode="download_only",
    )


def _coerce_persistent_remote_images(value: object) -> list[dict[str, str]] | None:
    if not isinstance(value, list) or not value:
        return None

    images: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        filename_obj = item.get("filename")
        if not isinstance(filename_obj, str) or not filename_obj:
            return None
        image_type_obj = item.get("type", "output")
        if image_type_obj != "output":
            return None
        image: dict[str, str] = {"filename": filename_obj, "type": "output"}
        subfolder_obj = item.get("subfolder")
        if isinstance(subfolder_obj, str) and subfolder_obj:
            image["subfolder"] = subfolder_obj
        images.append(image)
    return images


def _record_error_status_code(record: dict[str, object]) -> int | None:
    error_obj = record.get("error")
    if not isinstance(error_obj, dict):
        return None
    context_obj = error_obj.get("context")
    if not isinstance(context_obj, dict):
        return None
    status_code_obj = context_obj.get("status_code")
    if isinstance(status_code_obj, int) and not isinstance(status_code_obj, bool):
        return status_code_obj
    return None


def _fetch_remote_images_with_retry(
    *,
    base_url: str,
    prompt_id: str,
    request_timeout_s: float,
    job_timeout_s: float,
    get_history_item: Callable[..., dict[str, object]],
) -> list[dict[str, str]]:
    deadline = monotonic() + min(10.0, max(1.0, job_timeout_s))
    while True:
        history_item = get_history_item(
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


def _extract_y_prompt_ref(y_item: Any) -> dict[str, object] | None:
    value = getattr(y_item, "value", None)
    if not isinstance(value, dict):
        return None

    style_key = value.get(Y_STYLE_KEY)
    collection_id = value.get(Y_COLLECTION_ID)
    item_index_raw = value.get(Y_ITEM_INDEX)
    label = value.get("y")
    if (
        not isinstance(style_key, str)
        or not style_key.strip()
        or not isinstance(collection_id, str)
        or not collection_id.strip()
        or not isinstance(item_index_raw, str)
        or not item_index_raw.isdigit()
    ):
        return None

    ref: dict[str, object] = {
        "style_key": style_key.strip(),
        "collection_id": collection_id.strip(),
        "item_index": int(item_index_raw),
    }
    if isinstance(label, str):
        ref["label"] = label
    return ref


def _apply_y_prompt_ref(
    record: dict[str, object],
    y_prompt_ref: dict[str, object] | None,
) -> None:
    if y_prompt_ref is None:
        return
    record["y_style_key"] = y_prompt_ref["style_key"]
    record["y_collection_id"] = y_prompt_ref["collection_id"]
    record["y_item_index"] = y_prompt_ref["item_index"]


def _apply_mixer_prompt_parts(
    record: dict[str, object],
    *,
    artist_chain: str | None,
    y_common_prompt: str | None,
) -> None:
    record["artist_chain"] = artist_chain
    if artist_chain is not None or y_common_prompt is not None:
        record["y_common_prompt"] = y_common_prompt


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
    suffix = Path(image.get("filename", "")).suffix.lower()
    return suffix if suffix else ".png"


def _serialize_error(exc: Exception) -> dict[str, object]:
    as_metadata = getattr(exc, "as_metadata", None)
    if callable(as_metadata):
        payload = as_metadata()
        if isinstance(payload, dict):
            return cast(dict[str, object], _to_json_safe(payload))
    return {"type": exc.__class__.__name__, "message": str(exc)}


def _to_json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(v) for v in value]
    return str(value)
