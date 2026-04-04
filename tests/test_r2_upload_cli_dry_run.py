# pyright: basic, reportMissingImports=false

from __future__ import annotations

from argparse import Namespace
from contextlib import contextmanager
from collections.abc import Iterator
import json
import hashlib
import os
import sys
from pathlib import Path
from typing import cast

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.upload_images_to_r2 import main
from scripts.r2_upload.upload_planner import _build_run_db_fields
from scripts.r2_upload.upload_runtime import _resolve_image_workers


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_png(path: Path, *, size: tuple[int, int] = (8, 6)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, (10, 20, 30))
    image.save(path, format="PNG")


def _write_jpeg(path: Path, *, size: tuple[int, int] = (8, 6)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, (10, 20, 30))
    image.save(path, format="JPEG")


def _extended_run_json(
    *,
    run_dir: Path,
    run_dir_value: str | None = None,
    include_run_assets: bool = False,
    run_assets_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    run_name = run_dir_value if run_dir_value is not None else run_dir.name
    run_dir.mkdir(parents=True, exist_ok=True)
    workflow_download_path = run_dir / "workflow.json"
    workflow_download_path.write_text('{"version": 1}\n', encoding="utf-8")
    workflow_download_sha256 = _sha256_file(workflow_download_path)
    payload: dict[str, object] = {
        "run_id": run_name,
        "run_key": run_name,
        "run_dir": run_name,
        "dry_run": False,
        "config_schema_version": "image-run-config/v1",
        "config_path": "data/runs/example/config.yaml",
        "config_sha256": "deadbeef" * 8,
        "model": {
            "key": "chenkinnoob-xl-rf",
            "name": "ChenkinNoob XL Rectified Flow",
            "family": "stable-diffusion-xl",
            "links": {
                "homepage": None,
                "huggingface": None,
                "civitai": None,
            },
            "description": {
                "zh": "示例配置",
                "en": "Example config",
            },
        },
        "config_snapshot": {
            "prompts": {
                "x_path": "data/prompts/X/common_prompts.yaml",
                "y_path": "data/prompts/Y/300_NAI_Styles_Table-test.yaml",
                "x_sha256": "a" * 64,
                "y_sha256": "b" * 64,
            },
            "workflow": {
                "api_path": "data/runs/example/api.json",
                "api_sha256": "c" * 64,
                "download_path": "data/runs/example/workflow.json",
                "download_sha256": workflow_download_sha256,
                "ksampler_node_id": "6",
            },
            "generation": {
                "template": "{quality}{rating}{y}{gender}{characters}{series}{general}",
                "quality_prompt": "masterpiece, best quality,",
                "base_seed": 123,
                "negative_prompt": None,
                "append_negative_prompt": "nsfw, nipples, pussy, nude,",
                "width": 1024,
                "height": 1536,
                "batch_size": 1,
                "steps": 28,
                "cfg": 3.5,
                "denoise": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
            },
            "selection": {
                "x_limit": None,
                "y_limit": None,
                "x_indexes": None,
                "y_indexes": None,
            },
        },
        "workflow_download_path": str(workflow_download_path),
        "workflow_download_sha256": workflow_download_sha256,
    }
    if run_assets_payload is not None:
        payload["assets"] = run_assets_payload
    elif include_run_assets:
        cover_path = run_dir / "repo-assets/image.jpg"
        homepage_path = run_dir / "repo-assets/images/homepage.jpg"
        _write_jpeg(cover_path)
        _write_jpeg(homepage_path)
        payload["assets"] = {
            "cover_image": {
                "path": str(cover_path),
                "repo_relative_path": "data/runs/example/image.jpg",
                "sha256": _sha256_file(cover_path),
            },
            "homepage_images": [
                {
                    "path": str(homepage_path),
                    "repo_relative_path": "data/runs/example/images/homepage.jpg",
                    "sha256": _sha256_file(homepage_path),
                }
            ],
        }
    return payload


def _write_run_fixture(
    root: Path,
    *,
    run_name: str,
    use_multi_paths: bool = False,
    run_json_run_dir: str | None = None,
    include_run_assets: bool = False,
    run_assets_payload: dict[str, object] | None = None,
) -> Path:
    run_dir = root / run_name
    images_dir = run_dir / "images"
    images_dir.mkdir(parents=True)

    first = images_dir / "x0-y0.png"
    _write_png(first)

    metadata_record: dict[str, object] = {
        "status": "success",
        "x_index": 0,
        "y_index": 0,
        "local_image_path": "images/x0-y0.png",
    }

    if use_multi_paths:
        second = images_dir / "x0-y0-1.png"
        _write_png(second, size=(10, 8))
        metadata_record = {
            "status": "success",
            "x_index": 0,
            "y_index": 0,
            "local_image_paths": ["images/x0-y0.png", "images/x0-y0-1.png"],
        }

    (run_dir / "run.json").write_text(
        json.dumps(
            _extended_run_json(
                run_dir=run_dir,
                run_dir_value=run_json_run_dir,
                include_run_assets=include_run_assets,
                run_assets_payload=run_assets_payload,
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "metadata.jsonl").write_text(
        json.dumps(metadata_record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return run_dir


def _write_run_fixture_with_metadata_records(
    root: Path,
    *,
    run_name: str,
    metadata_records: list[dict[str, object]],
) -> Path:
    run_dir = root / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps(_extended_run_json(run_dir=run_dir), ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "metadata.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in metadata_records)
        + "\n",
        encoding="utf-8",
    )
    return run_dir


def _read_stdout_json(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    output = capsys.readouterr().out.strip()
    assert output
    lines = [line for line in output.splitlines() if line.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def test_cli_dry_run_outputs_required_keys_and_manifest_uploads(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="chenkinnoob-xl-rf")

    for key in [
        "R2_ENDPOINT",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_PUBLIC_BUCKET",
        "R2_PRIVATE_BUCKET",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)

    assert isinstance(payload.get("planned_grid_image_variant_uploads"), int)
    assert payload["planned_grid_image_variant_uploads"] == 4
    assert payload["planned_run_asset_variant_uploads"] == 0
    assert payload["planned_artifact_uploads"] == 1
    assert payload["planned_manifest_uploads"] == 2

    planned_uploads = payload.get("planned_uploads")
    assert isinstance(planned_uploads, list)
    assert len(planned_uploads) >= 6

    required_fields = {
        "bucket_scope",
        "key",
        "content_type",
        "cache_control",
        "byte_size",
    }
    for item in planned_uploads:
        assert isinstance(item, dict)
        assert required_fields.issubset(set(item.keys()))

    variant_names = {
        str(cast(dict[str, object], item).get("variant")) for item in planned_uploads
    }
    assert "workflow_download" in variant_names
    assert "manifest_public" in variant_names
    assert "manifest_private" in variant_names

    manifest_keys = payload.get("manifest_keys")
    assert isinstance(manifest_keys, dict)
    assert isinstance(manifest_keys.get("public"), list)
    assert isinstance(manifest_keys.get("private"), list)
    assert len(cast(list[object], manifest_keys["public"])) == 1
    assert len(cast(list[object], manifest_keys["private"])) == 1


def test_cli_dry_run_includes_cover_and_homepage_asset_variants(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="asset-run",
        include_run_assets=True,
    )

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("planned_grid_image_variant_uploads") == 4
    assert payload.get("planned_run_asset_variant_uploads") == 8
    assert payload.get("planned_artifact_uploads") == 1
    assert payload.get("planned_manifest_uploads") == 2

    planned_uploads = payload.get("planned_uploads")
    assert isinstance(planned_uploads, list)
    asset_keys = [
        str(cast(dict[str, object], item).get("key"))
        for item in planned_uploads
        if isinstance(item, dict)
    ]
    assert any("display_webp.webp" in key for key in asset_keys)
    assert any("thumb_avif.avif" in key for key in asset_keys)


def test_cli_dry_run_includes_png_cover_asset_variants_with_original_extension(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cover_path = tmp_path / "repo-assets/image.png"
    homepage_path = tmp_path / "repo-assets/images/card.jpeg"
    _write_png(cover_path)
    _write_jpeg(homepage_path)
    run_assets_payload = {
        "cover_image": {
            "path": str(cover_path),
            "repo_relative_path": "data/runs/custom/image.png",
            "sha256": _sha256_file(cover_path),
        },
        "homepage_images": [
            {
                "path": str(homepage_path),
                "repo_relative_path": "data/runs/custom/images/card.jpeg",
                "sha256": _sha256_file(homepage_path),
            }
        ],
    }
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="png-cover-run",
        run_assets_payload=run_assets_payload,
    )

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("planned_run_asset_variant_uploads") == 8

    planned_uploads = payload.get("planned_uploads")
    assert isinstance(planned_uploads, list)
    planned_asset_keys = [
        str(cast(dict[str, object], item).get("key"))
        for item in planned_uploads
        if isinstance(item, dict)
    ]
    assert any("display_webp.webp" in key for key in planned_asset_keys)
    assert any("thumb_webp.webp" in key for key in planned_asset_keys)


def test_build_run_db_fields_extracts_model_structured_fields(tmp_path: Path) -> None:
    run_dir = tmp_path / "model-run"
    fields = _build_run_db_fields(
        _extended_run_json(run_dir=run_dir), run_dir_name=run_dir.name
    )

    assert fields["run_id"] == "model-run"
    assert fields["model_name"] == "ChenkinNoob XL Rectified Flow"
    assert fields["model_description_zh"] == "示例配置"
    assert fields["model_description_en"] == "Example config"
    assert fields["model_homepage"] is None
    assert fields["model_huggingface"] is None
    assert fields["model_civitai"] is None
    expected_sha256 = _sha256_file(run_dir / "workflow.json")
    assert fields["workflow_download_r2_key"] == (
        f"runs/model-run/artifacts/workflow/{expected_sha256}.json"
    )
    assert fields["workflow_download_sha256"] == expected_sha256


def test_build_run_db_fields_skips_workflow_download_when_only_sha_present() -> None:
    fields = _build_run_db_fields(
        {
            "run_id": "model-run",
            "workflow_download_sha256": "a" * 64,
        },
        run_dir_name="model-run",
    )

    assert fields["workflow_download_r2_key"] is None
    assert fields["workflow_download_sha256"] == "a" * 64


def test_build_run_db_fields_workflow_key_changes_when_content_changes(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "model-run"
    payload = _extended_run_json(run_dir=run_dir)
    first_fields = _build_run_db_fields(payload, run_dir_name=run_dir.name)

    workflow_download_path = run_dir / "workflow.json"
    workflow_download_path.write_text('{"version": 2}\n', encoding="utf-8")
    new_sha256 = _sha256_file(workflow_download_path)
    payload["workflow_download_sha256"] = new_sha256

    config_snapshot = payload.get("config_snapshot")
    assert isinstance(config_snapshot, dict)
    workflow_snapshot = config_snapshot.get("workflow")
    assert isinstance(workflow_snapshot, dict)
    workflow_snapshot["download_sha256"] = new_sha256

    second_fields = _build_run_db_fields(payload, run_dir_name=run_dir.name)

    assert (
        first_fields["workflow_download_r2_key"]
        != second_fields["workflow_download_r2_key"]
    )


def test_cli_dry_run_fails_when_workflow_download_sha_mismatches(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="workflow-sha-mismatch-run")
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert isinstance(run_payload, dict)
    run_payload["workflow_download_sha256"] = "0" * 64
    config_snapshot = run_payload.get("config_snapshot")
    assert isinstance(config_snapshot, dict)
    workflow_snapshot = config_snapshot.get("workflow")
    assert isinstance(workflow_snapshot, dict)
    workflow_snapshot["download_sha256"] = "0" * 64
    (run_dir / "run.json").write_text(
        json.dumps(run_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])
    payload = _read_stdout_json(capsys)

    assert exit_code != 0
    assert payload.get("mode") == "error"
    assert "sha256 校验失败" in str(payload.get("message"))


def test_cli_default_selects_latest_run_under_run_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_root = tmp_path / "outputs"
    _ = _write_run_fixture(run_root, run_name="alpha-run")
    _ = _write_run_fixture(run_root, run_name="beta-run")

    exit_code = main(["--dry-run", "--run-root", str(run_root)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("run_dirs") == ["beta-run"]


def test_cli_dry_run_limit_applies_to_resolved_metadata_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_root = tmp_path / "outputs"
    run_dir = _write_run_fixture(
        run_root,
        run_name="limit-run",
        use_multi_paths=True,
    )

    exit_code = main(
        [
            "--dry-run",
            "--run-dir",
            str(run_dir),
            "--limit",
            "1",
        ]
    )

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("processed_grid_images") == 1
    assert payload.get("planned_grid_image_variant_uploads") == 4


def test_cli_run_dir_can_be_name_when_run_root_is_provided(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_root = tmp_path / "outputs"
    _ = _write_run_fixture(run_root, run_name="selected-run")

    exit_code = main(
        [
            "--dry-run",
            "--run-root",
            str(run_root),
            "--run-dir",
            "selected-run",
        ]
    )

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("run_dirs") == ["selected-run"]


def test_cli_dry_run_uses_run_dir_from_current_directory_name(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_root = tmp_path / "outputs"
    run_dir = _write_run_fixture(
        run_root,
        run_name="custom-folder-name",
        run_json_run_dir="custom-folder-name",
    )

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("run_dirs") == ["custom-folder-name"]
    planned_uploads = payload.get("planned_uploads")
    assert isinstance(planned_uploads, list)
    assert planned_uploads
    assert all(
        "custom-folder-name" in str(item.get("key"))
        for item in planned_uploads
        if isinstance(item, dict)
    )


def test_cli_dry_run_writes_intermediate_variants_to_env_dir(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="intermediate-run")
    intermediate_root = tmp_path / "custom-intermediate"
    monkeypatch.setenv("R2_UPLOAD_INTERMEDIATE_DIR", str(intermediate_root))

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)

    expected_run_intermediate = intermediate_root / "intermediate-run"
    assert payload.get("intermediate_dirs") == [str(expected_run_intermediate)]

    files = [item for item in expected_run_intermediate.iterdir() if item.is_file()]
    variant_files = [item for item in files if item.suffix in {".webp", ".avif"}]
    sidecar_files = [item for item in files if item.suffix == ".json"]
    assert len(variant_files) == 4
    assert len(sidecar_files) == 1


def test_cli_dry_run_reuses_cached_variants_without_reencoding(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="cache-run")

    first_exit = main(["--dry-run", "--run-dir", str(run_dir)])
    assert first_exit == 0
    _ = _read_stdout_json(capsys)

    def _fail_reencode(_: Path) -> list[dict[str, object]]:
        raise AssertionError("plan_image_variants should not run when cache exists")

    def _fail_metadata(_: Path) -> dict[str, object]:
        raise AssertionError(
            "inspect_image_metadata should not run when cache sidecar exists"
        )

    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.plan_image_variants",
        _fail_reencode,
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_planner.inspect_image_metadata",
        _fail_metadata,
    )

    second_exit = main(["--dry-run", "--run-dir", str(run_dir)])
    assert second_exit == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("processed_grid_images") == 1


def test_cli_dry_run_loads_metadata_once_per_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.r2_upload import upload_planner as upload_planner_module

    run_dir = _write_run_fixture(tmp_path, run_name="metadata-once-run")
    original_loader = upload_planner_module._load_metadata_records
    load_count = 0

    def _counting_loader(run_path: Path) -> list[dict[str, object]]:
        nonlocal load_count
        load_count += 1
        return original_loader(run_path)

    monkeypatch.setattr(
        upload_planner_module, "_load_metadata_records", _counting_loader
    )

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    _ = _read_stdout_json(capsys)
    assert load_count == 1


def test_cli_dry_run_cache_sidecars_do_not_collide_for_repeated_batch_index(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = tmp_path / "duplicate-batch-run"
    images_dir = run_dir / "images"
    images_dir.mkdir(parents=True)
    _write_png(images_dir / "a.png", size=(8, 6))
    _write_png(images_dir / "b.png", size=(10, 8))
    run_dir = _write_run_fixture_with_metadata_records(
        tmp_path,
        run_name="duplicate-batch-run",
        metadata_records=[
            {
                "status": "success",
                "x_index": 0,
                "y_index": 0,
                "batch_index": 0,
                "local_image_path": "images/a.png",
            },
            {
                "status": "success",
                "x_index": 1,
                "y_index": 0,
                "batch_index": 0,
                "local_image_path": "images/b.png",
            },
        ],
    )

    first_exit = main(["--dry-run", "--run-dir", str(run_dir)])
    assert first_exit == 0
    first_payload = _read_stdout_json(capsys)
    assert first_payload.get("processed_grid_images") == 2

    second_exit = main(["--dry-run", "--run-dir", str(run_dir)])
    assert second_exit == 0
    second_payload = _read_stdout_json(capsys)
    assert second_payload.get("processed_grid_images") == 2

    intermediate_dir = Path(cast(list[str], second_payload["intermediate_dirs"])[0])
    sidecars = sorted(item.name for item in intermediate_dir.glob("cache-*.json"))
    assert len(sidecars) == 2
    assert sidecars[0] != sidecars[1]


def test_cli_dry_run_rebuilds_cache_when_source_file_changes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="invalidate-cache-run")

    first_exit = main(["--dry-run", "--run-dir", str(run_dir)])
    assert first_exit == 0
    _ = _read_stdout_json(capsys)

    image_path = run_dir / "images/x0-y0.png"
    _write_png(image_path, size=(12, 10))

    from scripts.r2_upload import upload_images_to_r2 as upload_cli_module

    original_plan = upload_cli_module.plan_image_variants
    plan_calls = 0

    def _count_reencode(path: Path) -> list[dict[str, object]]:
        nonlocal plan_calls
        plan_calls += 1
        return original_plan(path)

    monkeypatch.setattr(upload_cli_module, "plan_image_variants", _count_reencode)

    second_exit = main(["--dry-run", "--run-dir", str(run_dir)])
    assert second_exit == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("processed_grid_images") == 1
    assert plan_calls == 1


def test_cli_uses_r2_image_workers_from_env(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="worker-run")
    monkeypatch.setenv("R2_IMAGE_WORKERS", "3")

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("processed_grid_images") == 1


def test_cli_rejects_invalid_r2_image_workers_env(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="invalid-worker-run")
    monkeypatch.setenv("R2_IMAGE_WORKERS", "0")

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 3
    payload = _read_stdout_json(capsys)
    assert payload.get("mode") == "error"
    assert payload.get("category") == "config"
    assert payload.get("exit_code") == 3


def test_resolve_image_workers_defaults_to_available_cpu_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("R2_IMAGE_WORKERS", raising=False)
    monkeypatch.setattr(os, "sched_getaffinity", lambda _: {0, 1, 2, 3})

    assert _resolve_image_workers(Namespace(concurrency=None)) == 4


def test_cli_dry_run_restores_visible_planning_progress_bar(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.r2_upload import upload_planner as upload_planner_module

    run_dir = _write_run_fixture(tmp_path, run_name="progress-bar-run")

    class _FakeTqdm:
        instances: list["_FakeTqdm"] = []

        def __init__(
            self, *args: object, total: int | None = None, **kwargs: object
        ) -> None:
            _ = (args, kwargs)
            self.total = total
            self.n = 0
            self.refreshed_totals: list[int | None] = []
            self.__class__.instances.append(self)

        def __enter__(self) -> "_FakeTqdm":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            _ = (exc_type, exc, tb)

        def update(self, step: int = 1) -> None:
            self.n += step

        def refresh(self) -> None:
            self.refreshed_totals.append(self.total)

    @contextmanager
    def _noop_redirect() -> Iterator[None]:
        yield None

    monkeypatch.setattr(upload_planner_module, "tqdm", _FakeTqdm)
    monkeypatch.setattr(upload_planner_module, "logging_redirect_tqdm", _noop_redirect)

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    _ = _read_stdout_json(capsys)
    assert len(_FakeTqdm.instances) == 1
    progress = _FakeTqdm.instances[0]
    assert progress.total == 1
    assert progress.n == 1
    assert progress.refreshed_totals == [1]
