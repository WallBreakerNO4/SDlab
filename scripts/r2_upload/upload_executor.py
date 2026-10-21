# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from typing import cast

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from .manifest import rewrite_current_manifest_status
from .r2_client import R2Client, UploadPlan
from .run_assets import asset_scan_report
from .supabase_writer import SupabaseWriter, estimate_upload_index_records
from .upload_contracts import (
    BucketScope,
    EvaluationStatus,
    EVALUATION_STATUS_COMPLETE,
    PlannedUpload,
    RunPlan,
    UploadScriptError,
    EVALUATION_STATUSES,
    snapshot_stats_report,
)

LOG = logging.getLogger(__name__)


def _upload_if_missing(
    *,
    r2_client: R2Client,
    bucket_names: dict[BucketScope, str],
    planned: PlannedUpload,
) -> bool:
    bucket_name = bucket_names[planned.bucket_scope]
    if r2_client.head_exists(
        bucket_name,
        planned.key,
        bucket_scope=planned.bucket_scope,
    ):
        return False

    _upload_planned(
        r2_client=r2_client,
        bucket_name=bucket_name,
        planned=planned,
    )
    return True


def _upload_planned(
    *,
    r2_client: R2Client,
    bucket_name: str,
    planned: PlannedUpload,
) -> None:
    r2_client.upload(
        UploadPlan(
            bucket_name=bucket_name,
            bucket_scope=planned.bucket_scope,
            key=planned.key,
            content_type=planned.content_type,
            cache_control=planned.cache_control,
            body_bytes=planned.body_bytes,
            local_path=planned.local_path,
        )
    )


def _current_manifest_upload(plan: RunPlan) -> PlannedUpload:
    matches = [
        upload for upload in plan.manifest_uploads if upload.variant == "view_current"
    ]
    if len(matches) != 1:
        raise RuntimeError("run plan must contain exactly one view_current upload")
    return matches[0]


@dataclass(frozen=True)
class _CurrentManifestFacts:
    release_id: str | None
    status: EvaluationStatus | None
    generated_cells: int | None


def _parse_current_manifest(payload: bytes | None) -> _CurrentManifestFacts:
    """解析发布视图当前指针（view/current.json）；字段缺失或不可用时为 None。"""
    empty = _CurrentManifestFacts(release_id=None, status=None, generated_cells=None)
    if payload is None:
        return empty
    try:
        parsed = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return empty
    if not isinstance(parsed, dict):
        return empty

    release_id_raw = parsed.get("release_id")
    release_id = (
        release_id_raw.strip()
        if isinstance(release_id_raw, str) and release_id_raw.strip()
        else None
    )

    status_raw = parsed.get("status")
    status = (
        cast(EvaluationStatus, status_raw)
        if isinstance(status_raw, str) and status_raw in EVALUATION_STATUSES
        else None
    )

    generated_cells_raw = parsed.get("generated_cells")
    generated_cells = (
        generated_cells_raw
        if isinstance(generated_cells_raw, int)
        and not isinstance(generated_cells_raw, bool)
        and generated_cells_raw >= 0
        else None
    )

    return _CurrentManifestFacts(
        release_id=release_id,
        status=status,
        generated_cells=generated_cells,
    )


def _effective_snapshot_status(
    *,
    planned_status: EvaluationStatus,
    remote_facts: _CurrentManifestFacts | None,
) -> EvaluationStatus:
    if remote_facts is None:
        return planned_status
    # 缺少状态字段的历史发布数据统一视为已完结；已完结状态单调不回退。
    if (
        remote_facts.status is None
        or remote_facts.status == EVALUATION_STATUS_COMPLETE
    ):
        return EVALUATION_STATUS_COMPLETE
    return planned_status


def _apply_status_monotonicity(
    *,
    plan: RunPlan,
    current_upload: PlannedUpload,
    remote_facts: _CurrentManifestFacts | None,
) -> tuple[PlannedUpload, EvaluationStatus]:
    effective_status = _effective_snapshot_status(
        planned_status=plan.snapshot_status,
        remote_facts=remote_facts,
    )
    if effective_status == plan.snapshot_status:
        return current_upload, effective_status

    body_bytes = current_upload.body_bytes
    if body_bytes is None:
        raise RuntimeError("planned current manifest is missing body bytes")
    updated_bytes = rewrite_current_manifest_status(
        body_bytes, status=effective_status
    )
    return (
        replace(
            current_upload,
            body_bytes=updated_bytes,
            byte_size=len(updated_bytes),
        ),
        effective_status,
    )


def _resolve_current_publish(
    *,
    plan: RunPlan,
    current_upload: PlannedUpload,
    r2_client: R2Client,
    bucket_names: dict[BucketScope, str],
    force_publish: bool,
) -> tuple[PlannedUpload, EvaluationStatus, bool]:
    """返回（状态收口后的当前指针上传、生效状态、是否需要上传指针）。

    同一评测的再次发布默认自动取代网站当前快照；仅当本次快照的已产出格数
    少于网站当前快照（快照回退）且未显式强推时拒绝。历史当前快照缺少
    `generated_cells` 时跳过回退检查；内容无变化时不上传新指针。
    """
    if _parse_current_manifest(current_upload.body_bytes).release_id is None:
        raise RuntimeError("planned current manifest is invalid")

    bucket_name = bucket_names[current_upload.bucket_scope]
    remote_payload = r2_client.read_bytes_if_exists(
        bucket_name,
        current_upload.key,
        bucket_scope=current_upload.bucket_scope,
    )
    remote_facts = (
        None if remote_payload is None else _parse_current_manifest(remote_payload)
    )

    if (
        remote_facts is not None
        and remote_facts.generated_cells is not None
        and plan.generated_cells < remote_facts.generated_cells
        and not force_publish
    ):
        raise UploadScriptError(
            (
                f"run_dir={plan.run_dir_name} 本次快照已产出 "
                f"{plan.generated_cells} 格，少于网站当前快照的 "
                f"{remote_facts.generated_cells} 格；快照回退需使用 "
                "-F/--force-publish"
            ),
            category="argument",
        )

    effective_upload, effective_status = _apply_status_monotonicity(
        plan=plan,
        current_upload=current_upload,
        remote_facts=remote_facts,
    )
    if remote_payload is None:
        return effective_upload, effective_status, True
    return (
        effective_upload,
        effective_status,
        remote_payload != effective_upload.body_bytes,
    )


def _upload_image_variants_for_plan(
    *,
    plan: RunPlan,
    upload_concurrency: int,
    r2_client: R2Client,
    bucket_names: dict[BucketScope, str],
    image_pbar: tqdm,
    thread_pool_cls: type[ThreadPoolExecutor],
) -> tuple[int, int]:
    uploaded = 0
    skipped_existing = 0
    with thread_pool_cls(max_workers=upload_concurrency) as pool:
        futures: list[Future[bool]] = [
            pool.submit(
                _upload_if_missing,
                r2_client=r2_client,
                bucket_names=bucket_names,
                planned=upload,
            )
            for upload in plan.image_uploads
        ]
        for future in as_completed(futures):
            if future.result():
                uploaded += 1
            else:
                skipped_existing += 1
            image_pbar.update(1)
    return uploaded, skipped_existing


def _upload_artifacts_for_plan(
    *,
    plan: RunPlan,
    upload_concurrency: int,
    r2_client: R2Client,
    bucket_names: dict[BucketScope, str],
    artifact_pbar: tqdm,
    thread_pool_cls: type[ThreadPoolExecutor],
) -> tuple[int, int]:
    artifact_uploaded = 0
    skipped_existing = 0
    uploads = [
        *plan.artifact_uploads,
        *(
            upload
            for upload in plan.manifest_uploads
            if upload.variant != "view_current"
        ),
    ]
    if not uploads:
        return artifact_uploaded, skipped_existing

    with thread_pool_cls(max_workers=upload_concurrency) as pool:
        futures: list[Future[bool]] = [
            pool.submit(
                _upload_if_missing,
                r2_client=r2_client,
                bucket_names=bucket_names,
                planned=upload,
            )
            for upload in uploads
        ]
        for future in as_completed(futures):
            if future.result():
                artifact_uploaded += 1
            else:
                skipped_existing += 1
            artifact_pbar.update(1)
    return artifact_uploaded, skipped_existing


def _execute(
    plans: list[RunPlan],
    *,
    bucket_names: dict[BucketScope, str],
    upload_concurrency: int,
    r2_client_factory: Callable[[], R2Client],
    supabase_writer_factory: Callable[[], SupabaseWriter],
    thread_pool_cls: type[ThreadPoolExecutor] = ThreadPoolExecutor,
    force_publish: bool,
) -> dict[str, object]:
    r2_client = r2_client_factory()
    supabase_writer = supabase_writer_factory()

    uploaded = 0
    skipped_existing = 0
    artifact_uploaded = 0
    processed_images = 0

    total_image_uploads = sum(len(plan.image_uploads) for plan in plans)
    total_artifact_uploads = sum(
        len(plan.artifact_uploads) + len(plan.manifest_uploads) for plan in plans
    )

    total_db_records = 0
    for plan in plans:
        total_db_records += estimate_upload_index_records(plan.upload_index_payload)

    publish_current_by_run: dict[str, bool] = {}
    current_upload_by_run: dict[str, PlannedUpload] = {}
    effective_status_by_run: dict[str, EvaluationStatus] = {}
    for plan in plans:
        current_upload = _current_manifest_upload(plan)
        (
            effective_upload,
            effective_status,
            should_publish,
        ) = _resolve_current_publish(
            plan=plan,
            current_upload=current_upload,
            r2_client=r2_client,
            bucket_names=bucket_names,
            force_publish=force_publish,
        )
        if effective_status != plan.snapshot_status:
            plan.upload_index_payload["status"] = effective_status
        current_upload_by_run[plan.run_dir_name] = effective_upload
        publish_current_by_run[plan.run_dir_name] = should_publish
        effective_status_by_run[plan.run_dir_name] = effective_status

    LOG.info(
        "start upload execution: run_count=%s image_upload_count=%s artifact_upload_count=%s db_record_count=%s upload_concurrency=%s",
        len(plans),
        total_image_uploads,
        total_artifact_uploads,
        total_db_records,
        upload_concurrency,
    )

    with logging_redirect_tqdm():
        with tqdm(
            total=total_image_uploads,
            desc="图片上传",
            unit="image",
            dynamic_ncols=True,
        ) as image_pbar:
            with tqdm(
                total=total_artifact_uploads,
                desc="资源上传",
                unit="artifact",
                dynamic_ncols=True,
            ) as artifact_pbar:
                with tqdm(
                    total=total_db_records,
                    desc="数据上传",
                    unit="record",
                    dynamic_ncols=True,
                ) as db_pbar:

                    def _tick_db_progress() -> None:
                        db_pbar.update(1)

                    for plan in plans:
                        processed_images += plan.processed_images

                        plan_uploaded, plan_skipped = _upload_image_variants_for_plan(
                            plan=plan,
                            upload_concurrency=upload_concurrency,
                            r2_client=r2_client,
                            bucket_names=bucket_names,
                            image_pbar=image_pbar,
                            thread_pool_cls=thread_pool_cls,
                        )
                        uploaded += plan_uploaded
                        skipped_existing += plan_skipped

                        (
                            plan_artifact_uploaded,
                            plan_artifact_skipped,
                        ) = _upload_artifacts_for_plan(
                            plan=plan,
                            upload_concurrency=upload_concurrency,
                            r2_client=r2_client,
                            bucket_names=bucket_names,
                            artifact_pbar=artifact_pbar,
                            thread_pool_cls=thread_pool_cls,
                        )
                        artifact_uploaded += plan_artifact_uploaded
                        skipped_existing += plan_artifact_skipped

                        supabase_writer.upsert_upload_index(
                            plan.upload_index_payload,
                            progress_callback=_tick_db_progress,
                        )

                        current_upload = current_upload_by_run[plan.run_dir_name]
                        if publish_current_by_run[plan.run_dir_name]:
                            _upload_planned(
                                r2_client=r2_client,
                                bucket_name=bucket_names[
                                    current_upload.bucket_scope
                                ],
                                planned=current_upload,
                            )
                            artifact_uploaded += 1
                        else:
                            skipped_existing += 1
                        artifact_pbar.update(1)

                    image_pbar.set_postfix(
                        uploaded=uploaded,
                        skipped=skipped_existing,
                        refresh=False,
                    )
    LOG.info(
        "upload execution done: uploaded=%s skipped_existing=%s artifact_uploaded=%s",
        uploaded,
        skipped_existing,
        artifact_uploaded,
    )

    return {
        "mode": "execute",
        "run_count": len(plans),
        "run_dirs": [plan.run_dir_name for plan in plans],
        "asset_scans": [
            asset_scan_report(plan.run_dir_name, plan.asset_scan) for plan in plans
        ],
        "snapshot_stats": [
            snapshot_stats_report(
                plan,
                status=effective_status_by_run[plan.run_dir_name],
            )
            for plan in plans
        ],
        "processed_grid_images": processed_images,
        "uploaded_variant_uploads": uploaded,
        "uploaded_artifact_uploads": artifact_uploaded,
        "skipped_existing_uploads": skipped_existing,
        "db_run_upserts": len(plans),
        "force_publish": force_publish,
    }
