# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from .r2_client import R2Client, UploadPlan
from .supabase_writer import SupabaseWriter
from .upload_contracts import BucketScope, PlannedUpload, RunPlan

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
    return True


def _execute(
    plans: list[RunPlan],
    *,
    bucket_names: dict[BucketScope, str],
    upload_concurrency: int,
    r2_client_factory: Callable[[], R2Client],
    supabase_writer_factory: Callable[[], SupabaseWriter],
    thread_pool_cls: type[ThreadPoolExecutor] = ThreadPoolExecutor,
) -> dict[str, object]:
    r2_client = r2_client_factory()
    supabase_writer = supabase_writer_factory()

    uploaded = 0
    skipped_existing = 0
    manifest_uploaded = 0
    processed_images = 0

    total_image_uploads = sum(len(plan.image_uploads) for plan in plans)
    total_manifest_uploads = sum(len(plan.manifest_uploads) for plan in plans)

    total_db_records = 0
    for plan in plans:
        images_raw = plan.upload_index_payload.get("images")
        images_list = images_raw if isinstance(images_raw, list) else []
        total_db_records += 1 + len(images_list)
        for image in images_list:
            if not isinstance(image, dict):
                continue
            variants_raw = image.get("variants")
            variants_list = variants_raw if isinstance(variants_raw, list) else []
            total_db_records += len(variants_list)

    LOG.info(
        "start upload execution: run_count=%s image_upload_count=%s manifest_upload_count=%s db_record_count=%s upload_concurrency=%s",
        len(plans),
        total_image_uploads,
        total_manifest_uploads,
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
                total=total_manifest_uploads,
                desc="清单上传",
                unit="manifest",
                dynamic_ncols=True,
            ) as manifest_pbar:
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

                        supabase_writer.upsert_upload_index(
                            plan.upload_index_payload,
                            progress_callback=_tick_db_progress,
                        )

                        for manifest_upload in plan.manifest_uploads:
                            if _upload_if_missing(
                                r2_client=r2_client,
                                bucket_names=bucket_names,
                                planned=manifest_upload,
                            ):
                                manifest_uploaded += 1
                            else:
                                skipped_existing += 1
                            manifest_pbar.update(1)

                    image_pbar.set_postfix(
                        uploaded=uploaded,
                        skipped=skipped_existing,
                        refresh=False,
                    )
    LOG.info(
        "upload execution done: uploaded=%s skipped_existing=%s manifest_uploaded=%s",
        uploaded,
        skipped_existing,
        manifest_uploaded,
    )

    return {
        "mode": "execute",
        "run_count": len(plans),
        "run_dirs": [plan.run_dir_name for plan in plans],
        "processed_images": processed_images,
        "uploaded": uploaded,
        "skipped_existing": skipped_existing,
        "db_upserts": len(plans),
        "manifest_uploaded": manifest_uploaded,
    }
