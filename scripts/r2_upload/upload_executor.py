# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from .r2_client import R2Client, UploadPlan
from .supabase_writer import SupabaseWriter, estimate_upload_index_records
from .upload_contracts import (
    BucketScope,
    PlannedUpload,
    RunPlan,
    UploadScriptError,
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


def _manifest_release_id(payload: bytes | None) -> str | None:
    if payload is None:
        return None
    try:
        parsed = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    release_id = parsed.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        return None
    return release_id.strip()


def _should_publish_current(
    *,
    plan: RunPlan,
    current_upload: PlannedUpload,
    r2_client: R2Client,
    bucket_names: dict[BucketScope, str],
    force_publish: bool,
) -> bool:
    planned_release_id = _manifest_release_id(current_upload.body_bytes)
    if planned_release_id is None:
        raise RuntimeError("planned current manifest is invalid")

    bucket_name = bucket_names[current_upload.bucket_scope]
    remote_payload = r2_client.read_bytes_if_exists(
        bucket_name,
        current_upload.key,
        bucket_scope=current_upload.bucket_scope,
    )
    if remote_payload is None:
        return True

    remote_release_id = _manifest_release_id(remote_payload)
    if remote_release_id == planned_release_id:
        return False
    if force_publish:
        return True

    raise UploadScriptError(
        f"run_dir={plan.run_dir_name} 已发布不同 release；请使用 -F/--force-publish",
        category="argument",
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
    for plan in plans:
        current_upload = _current_manifest_upload(plan)
        current_upload_by_run[plan.run_dir_name] = current_upload
        publish_current_by_run[plan.run_dir_name] = _should_publish_current(
            plan=plan,
            current_upload=current_upload,
            r2_client=r2_client,
            bucket_names=bucket_names,
            force_publish=force_publish,
        )

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
        "processed_grid_images": processed_images,
        "uploaded_variant_uploads": uploaded,
        "uploaded_artifact_uploads": artifact_uploaded,
        "skipped_existing_uploads": skipped_existing,
        "db_run_upserts": len(plans),
        "force_publish": force_publish,
    }
