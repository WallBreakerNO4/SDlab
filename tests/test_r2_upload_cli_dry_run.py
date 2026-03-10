# pyright: basic, reportMissingImports=false

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.upload_images_to_r2 import main


def _write_png(path: Path, *, size: tuple[int, int] = (8, 6)) -> None:
    image = Image.new("RGB", size, (10, 20, 30))
    image.save(path, format="PNG")


def _extended_run_json(
    *, run_dir: Path, run_dir_value: str | None = None
) -> dict[str, object]:
    return {
        "run_id": "test-run-id",
        "run_dir": run_dir_value if run_dir_value is not None else str(run_dir),
        "dry_run": False,
        "config_schema_version": "image-run-config/v1",
        "config_path": "data/runs/example.yaml",
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
                "path": "data/comfyui-flow/CKNOOBRF.json",
                "sha256": "c" * 64,
                "ksampler_node_id": "6",
            },
            "generation": {
                "template": "{gender}{characters}{series}{rating}{y}{general}{quality}",
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
    }


def _write_run_fixture(
    root: Path,
    *,
    run_name: str,
    use_multi_paths: bool = False,
    run_json_run_dir: str | None = None,
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
            _extended_run_json(run_dir=run_dir, run_dir_value=run_json_run_dir),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "metadata.jsonl").write_text(
        json.dumps(metadata_record, ensure_ascii=False) + "\n",
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
    run_dir = _write_run_fixture(tmp_path, run_name="run-20260221T120000Z")

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

    assert isinstance(payload.get("planned_variants"), int)
    assert payload["planned_variants"] == 5

    planned_uploads = payload.get("planned_uploads")
    assert isinstance(planned_uploads, list)
    assert len(planned_uploads) >= 7

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
    assert "manifest_public" in variant_names
    assert "manifest_private" in variant_names

    manifest_keys = payload.get("manifest_keys")
    assert isinstance(manifest_keys, dict)
    assert isinstance(manifest_keys.get("public"), list)
    assert isinstance(manifest_keys.get("private"), list)
    assert len(cast(list[object], manifest_keys["public"])) == 1
    assert len(cast(list[object], manifest_keys["private"])) == 1


def test_cli_default_selects_latest_run_under_run_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_root = tmp_path / "outputs"
    _ = _write_run_fixture(run_root, run_name="run-20260220T120000Z")
    _ = _write_run_fixture(run_root, run_name="run-20260221T120000Z")

    exit_code = main(["--dry-run", "--run-root", str(run_root)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("run_dirs") == ["run-20260221T120000Z"]


def test_cli_dry_run_limit_applies_to_resolved_metadata_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_root = tmp_path / "outputs"
    run_dir = _write_run_fixture(
        run_root,
        run_name="run-20260221T130000Z",
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
    assert payload.get("processed_images") == 1
    assert payload.get("planned_variants") == 5


def test_cli_run_dir_can_be_name_when_run_root_is_provided(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_root = tmp_path / "outputs"
    _ = _write_run_fixture(run_root, run_name="run-20260221T140000Z")

    exit_code = main(
        [
            "--dry-run",
            "--run-root",
            str(run_root),
            "--run-dir",
            "run-20260221T140000Z",
        ]
    )

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("run_dirs") == ["run-20260221T140000Z"]


def test_cli_dry_run_accepts_extended_run_json_with_run_dir_fallback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_root = tmp_path / "outputs"
    run_dir = _write_run_fixture(
        run_root,
        run_name="custom-folder-name",
        run_json_run_dir="comfyui_api_outputs/run-20260221T190000Z",
    )

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("run_dirs") == ["run-20260221T190000Z"]
    planned_uploads = payload.get("planned_uploads")
    assert isinstance(planned_uploads, list)
    assert planned_uploads
    assert all(
        "run-20260221T190000Z" in str(item.get("key"))
        for item in planned_uploads
        if isinstance(item, dict)
    )


def test_cli_dry_run_writes_intermediate_variants_to_env_dir(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="run-20260221T150000Z")
    intermediate_root = tmp_path / "custom-intermediate"
    monkeypatch.setenv("R2_UPLOAD_INTERMEDIATE_DIR", str(intermediate_root))

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)

    expected_run_intermediate = intermediate_root / "run-20260221T150000Z"
    assert payload.get("intermediate_dirs") == [str(expected_run_intermediate)]

    files = [item for item in expected_run_intermediate.iterdir() if item.is_file()]
    assert len(files) == 4
    suffixes = {item.suffix for item in files}
    assert suffixes == {".webp", ".avif"}


def test_cli_dry_run_reuses_cached_variants_without_reencoding(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="run-20260221T160000Z")

    first_exit = main(["--dry-run", "--run-dir", str(run_dir)])
    assert first_exit == 0
    _ = _read_stdout_json(capsys)

    def _fail_reencode(_: Path) -> list[dict[str, object]]:
        raise AssertionError("plan_image_variants should not run when cache exists")

    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.plan_image_variants",
        _fail_reencode,
    )

    second_exit = main(["--dry-run", "--run-dir", str(run_dir)])
    assert second_exit == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("processed_images") == 1


def test_cli_uses_r2_image_workers_from_env(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="run-20260221T170000Z")
    monkeypatch.setenv("R2_IMAGE_WORKERS", "3")

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0
    payload = _read_stdout_json(capsys)
    assert payload.get("processed_images") == 1


def test_cli_rejects_invalid_r2_image_workers_env(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="run-20260221T180000Z")
    monkeypatch.setenv("R2_IMAGE_WORKERS", "0")

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 3
    payload = _read_stdout_json(capsys)
    assert payload.get("mode") == "error"
    assert payload.get("category") == "config"
    assert payload.get("exit_code") == 3
