# pyright: basic, reportMissingImports=false

from __future__ import annotations

import json
import hashlib
import sys
from concurrent.futures import Future
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.upload_images_to_r2 import main


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_run_fixture(
    root: Path,
    *,
    run_name: str,
    include_workflow_download: bool = False,
    planned_cells: int | None = None,
) -> Path:
    run_dir = root / run_name
    images_dir = run_dir / "images"
    images_dir.mkdir(parents=True)

    image_path = images_dir / "x0-y0.png"
    Image.new("RGB", (8, 6), (23, 45, 67)).save(image_path, format="PNG")

    run_payload: dict[str, object] = {
        "run_id": run_name,
        "run_key": run_name,
        "run_dir": run_name,
        "created_at": "2026-01-01T00:00:00Z",
    }
    if planned_cells is not None:
        run_payload["selection"] = {
            "x_columns": [
                {"type": "normal", "description": {"zh": f"列 {index + 1}"}}
                for index in range(planned_cells)
            ],
            "y_indexes": [0],
            "x_count": planned_cells,
            "y_count": 1,
            "total_cells": planned_cells,
        }
    if include_workflow_download:
        workflow_download_path = run_dir / "workflow.json"
        workflow_download_path.write_text('{"version":1}\n', encoding="utf-8")
        workflow_download_sha256 = _sha256_file(workflow_download_path)
        run_payload["workflow_download_path"] = str(workflow_download_path)
        run_payload["workflow_download_sha256"] = workflow_download_sha256

    (run_dir / "run.json").write_text(
        json.dumps(run_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "metadata.jsonl").write_text(
        json.dumps(
            {
                "status": "success",
                "x_index": 0,
                "y_index": 0,
                "local_image_path": "images/x0-y0.png",
                "x_info_type": "normal",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_dir


def _append_cell_record(run_dir: Path, *, x_index: int) -> None:
    image_rel = f"images/x{x_index}-y0.png"
    Image.new("RGB", (8, 6), (10 + x_index, 20, 30)).save(
        run_dir / image_rel, format="PNG"
    )
    with (run_dir / "metadata.jsonl").open("a", encoding="utf-8") as handle:
        _ = handle.write(
            json.dumps(
                {
                    "status": "success",
                    "x_index": x_index,
                    "y_index": 0,
                    "local_image_path": image_rel,
                    "x_info_type": "normal",
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def _keep_only_first_cell(run_dir: Path) -> None:
    metadata_path = run_dir / "metadata.jsonl"
    kept = [
        line
        for line in metadata_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("x_index") == 0
    ]
    metadata_path.write_text("\n".join(kept) + "\n", encoding="utf-8")


class _FakeR2Client:
    def __init__(self) -> None:
        self._objects: set[tuple[str, str]] = set()
        self._object_bodies: dict[tuple[str, str], bytes] = {}
        self.upload_calls: int = 0
        self.uploaded_keys: list[tuple[str, str]] = []

    def body_for(self, bucket_name: str, key: str) -> bytes | None:
        return self._object_bodies.get((bucket_name, key))

    def seed_object(self, bucket_name: str, key: str, body: bytes) -> None:
        self._objects.add((bucket_name, key))
        self._object_bodies[(bucket_name, key)] = body

    def head_exists(self, bucket_name: str, key: str, *, bucket_scope: str) -> bool:
        _ = bucket_scope
        return (bucket_name, key) in self._objects

    def read_bytes_if_exists(
        self, bucket_name: str, key: str, *, bucket_scope: str
    ) -> bytes | None:
        _ = bucket_scope
        return self._object_bodies.get((bucket_name, key))

    def upload(self, plan: object) -> None:
        bucket_name = str(getattr(plan, "bucket_name"))
        key = str(getattr(plan, "key"))
        self.upload_calls += 1
        self.uploaded_keys.append((bucket_name, key))
        self._objects.add((bucket_name, key))
        body_bytes = getattr(plan, "body_bytes", None)
        self._object_bodies[(bucket_name, key)] = (
            body_bytes if isinstance(body_bytes, bytes) else b""
        )


class _FakeSupabaseError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("simulated db failure")
        self.category = "remote"


class _FakeSupabaseWriter:
    def __init__(self) -> None:
        self.calls: int = 0

    def upsert_upload_index(
        self,
        payload: dict[str, object],
        *,
        progress_callback: Callable[[], None] | None = None,
    ) -> None:
        self.calls += 1
        if self.calls == 1:
            raise _FakeSupabaseError()

        if progress_callback is None:
            return

        images_raw = payload.get("images")
        images_list = images_raw if isinstance(images_raw, list) else []
        total = 1 + len(images_list)
        for image in images_list:
            if not isinstance(image, dict):
                continue
            variants_raw = image.get("variants")
            variants_list = variants_raw if isinstance(variants_raw, list) else []
            total += len(variants_list)

        for _ in range(total):
            progress_callback()


class _NoopSupabaseWriter:
    def upsert_upload_index(
        self,
        payload: dict[str, object],
        *,
        progress_callback: Callable[[], None] | None = None,
    ) -> None:
        if progress_callback is None:
            return

        images_raw = payload.get("images")
        images_list = images_raw if isinstance(images_raw, list) else []
        total = 1 + len(images_list)
        for image in images_list:
            if not isinstance(image, dict):
                continue
            variants_raw = image.get("variants")
            variants_list = variants_raw if isinstance(variants_raw, list) else []
            total += len(variants_list)

        for _ in range(total):
            progress_callback()


class _CurrentOrderingSupabaseWriter(_NoopSupabaseWriter):
    def __init__(self, *, fake_r2: _FakeR2Client, public_bucket: str) -> None:
        self.fake_r2 = fake_r2
        self.public_bucket = public_bucket

    def upsert_upload_index(
        self,
        payload: dict[str, object],
        *,
        progress_callback: Callable[[], None] | None = None,
    ) -> None:
        run_dir = str(payload["run_dir"])
        current_ref = (
            self.public_bucket,
            f"runs/{run_dir}/view/current.json",
        )
        assert current_ref not in self.fake_r2._objects
        super().upsert_upload_index(
            payload,
            progress_callback=progress_callback,
        )


class _ArtifactAwareSupabaseWriter:
    def __init__(self, *, fake_r2: _FakeR2Client, public_bucket: str) -> None:
        self.fake_r2 = fake_r2
        self.public_bucket = public_bucket
        self.calls = 0

    def upsert_upload_index(
        self,
        payload: dict[str, object],
        *,
        progress_callback: Callable[[], None] | None = None,
    ) -> None:
        self.calls += 1
        workflow_key = payload.get("workflow_download_r2_key")
        assert isinstance(workflow_key, str)
        assert (self.public_bucket, workflow_key) in self.fake_r2._objects
        if progress_callback is None:
            return

        images_raw = payload.get("images")
        images_list = images_raw if isinstance(images_raw, list) else []
        total = 1 + len(images_list)
        for image in images_list:
            if not isinstance(image, dict):
                continue
            variants_raw = image.get("variants")
            variants_list = variants_raw if isinstance(variants_raw, list) else []
            total += len(variants_list)

        for _ in range(total):
            progress_callback()


class _CapturingExecutor:
    seen_max_workers: list[int] = []

    def __init__(self, *, max_workers: int) -> None:
        self.max_workers = max_workers
        self.seen_max_workers.append(max_workers)

    def __enter__(self) -> "_CapturingExecutor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        _ = (exc_type, exc, tb)

    def submit(
        self,
        fn: Callable[..., object],
        /,
        *args: object,
        **kwargs: object,
    ) -> Future[object]:
        future: Future[object] = Future()
        try:
            result = fn(*args, **kwargs)
            future.set_result(result)
        except Exception as exc:
            future.set_exception(exc)
        return future


def _read_stdout_json(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    output = capsys.readouterr().out.strip()
    assert output
    lines = [line for line in output.splitlines() if line.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def test_rerun_recovers_db_after_partial_failure_and_publishes_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="retry-db-recovery-run")

    monkeypatch.setenv("R2_PUBLIC_BUCKET", "dummy-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "dummy-private")

    fake_r2 = _FakeR2Client()
    fake_writer = _FakeSupabaseWriter()

    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.SupabaseWriter.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_writer),
    )

    first_exit = main(["--run-dir", str(run_dir)])
    first_payload = _read_stdout_json(capsys)

    assert first_exit == 8
    assert first_payload.get("mode") == "error"
    assert first_payload.get("category") == "remote"
    assert first_payload.get("exit_code") == 8
    assert fake_r2.upload_calls > 0

    uploaded_after_first = fake_r2.upload_calls

    second_exit = main(["--run-dir", str(run_dir)])
    second_payload = _read_stdout_json(capsys)

    assert second_exit == 0
    assert second_payload.get("mode") == "execute"
    assert fake_writer.calls == 2
    assert fake_r2.upload_calls == uploaded_after_first + 1

    key_counts: dict[tuple[str, str], int] = {}
    for object_ref in fake_r2.uploaded_keys:
        key_counts[object_ref] = key_counts.get(object_ref, 0) + 1
    assert all(count == 1 for count in key_counts.values())


def test_execute_uses_r2_upload_concurrency_from_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="upload-concurrency-run")

    monkeypatch.setenv("R2_PUBLIC_BUCKET", "dummy-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "dummy-private")
    monkeypatch.setenv("R2_UPLOAD_CONCURRENCY", "4")

    fake_r2 = _FakeR2Client()

    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.SupabaseWriter.from_env",
        classmethod(lambda cls, dry_run, **kwargs: _NoopSupabaseWriter()),
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.ThreadPoolExecutor",
        _CapturingExecutor,
    )

    exit_code = main(["--run-dir", str(run_dir)])
    payload = _read_stdout_json(capsys)

    assert exit_code == 0
    assert payload.get("mode") == "execute"
    assert 4 in _CapturingExecutor.seen_max_workers


def _current_manifest(fake_r2: _FakeR2Client, run_dir_name: str) -> dict[str, object]:
    body = fake_r2.body_for("dummy-public", f"runs/{run_dir_name}/view/current.json")
    assert body is not None
    parsed = json.loads(body.decode("utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def test_changed_release_replaces_current_snapshot_without_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="auto-replace-run")
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "dummy-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "dummy-private")
    fake_r2 = _FakeR2Client()

    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.SupabaseWriter.from_env",
        classmethod(lambda cls, dry_run, **kwargs: _NoopSupabaseWriter()),
    )

    assert main(["--run-dir", str(run_dir)]) == 0
    first_payload = _read_stdout_json(capsys)
    assert first_payload["force_publish"] is False
    first_manifest = _current_manifest(fake_r2, "auto-replace-run")
    uploads_after_first = fake_r2.upload_calls

    # 格数持平、内容变化：不需要 -F，自动取代当前快照。
    metadata_path = run_dir / "metadata.jsonl"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["positive_prompt"] = "changed prompt"
    metadata["prompt_hash"] = "changed-hash"
    metadata_path.write_text(json.dumps(metadata) + "\n", encoding="utf-8")

    assert main(["--run-dir", str(run_dir)]) == 0
    second_payload = _read_stdout_json(capsys)
    assert second_payload["mode"] == "execute"
    assert second_payload["force_publish"] is False
    assert fake_r2.upload_calls > uploads_after_first

    second_manifest = _current_manifest(fake_r2, "auto-replace-run")
    assert second_manifest["release_id"] != first_manifest["release_id"]

    # 内容无变化的重复发布：不产生新版本、不写新对象。
    uploads_after_second = fake_r2.upload_calls
    assert main(["--run-dir", str(run_dir)]) == 0
    _ = _read_stdout_json(capsys)
    assert fake_r2.upload_calls == uploads_after_second
    assert _current_manifest(fake_r2, "auto-replace-run") == second_manifest


def test_cell_growth_replaces_current_snapshot_without_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="cell-growth-run",
        planned_cells=2,
    )
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "dummy-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "dummy-private")
    fake_r2 = _FakeR2Client()

    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.SupabaseWriter.from_env",
        classmethod(lambda cls, dry_run, **kwargs: _NoopSupabaseWriter()),
    )

    assert main(["--run-dir", str(run_dir)]) == 0
    _ = _read_stdout_json(capsys)
    first_manifest = _current_manifest(fake_r2, "cell-growth-run")
    assert first_manifest["generated_cells"] == 1
    assert first_manifest["status"] == "in_progress"

    # 补上第二格：格数增加，仍然不需要 -F。
    _append_cell_record(run_dir, x_index=1)

    assert main(["--run-dir", str(run_dir)]) == 0
    payload = _read_stdout_json(capsys)
    assert payload["force_publish"] is False
    assert payload["snapshot_stats"] == [
        {
            "run_dir": "cell-growth-run",
            "status": "complete",
            "generated_cells": 2,
            "planned_cells": 2,
        }
    ]

    second_manifest = _current_manifest(fake_r2, "cell-growth-run")
    assert second_manifest["release_id"] != first_manifest["release_id"]
    assert second_manifest["generated_cells"] == 2
    assert second_manifest["status"] == "complete"


def test_snapshot_rollback_requires_force_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="rollback-run",
        planned_cells=2,
    )
    _append_cell_record(run_dir, x_index=1)
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "dummy-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "dummy-private")
    fake_r2 = _FakeR2Client()

    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.SupabaseWriter.from_env",
        classmethod(lambda cls, dry_run, **kwargs: _NoopSupabaseWriter()),
    )

    assert main(["--run-dir", str(run_dir)]) == 0
    _ = _read_stdout_json(capsys)
    first_manifest = _current_manifest(fake_r2, "rollback-run")
    assert first_manifest["generated_cells"] == 2
    uploads_after_first = fake_r2.upload_calls

    # 格数变少：拒绝并要求显式 -F，当前快照与对象均不变。
    _keep_only_first_cell(run_dir)

    assert main(["--run-dir", str(run_dir)]) == 2
    rejected_payload = _read_stdout_json(capsys)
    assert rejected_payload["category"] == "argument"
    assert "-F/--force-publish" in str(rejected_payload["message"])
    assert fake_r2.upload_calls == uploads_after_first
    assert _current_manifest(fake_r2, "rollback-run") == first_manifest

    # 显式强推后生效；已完结状态单调不回退。
    assert main(["-F", "--run-dir", str(run_dir)]) == 0
    forced_payload = _read_stdout_json(capsys)
    assert forced_payload["force_publish"] is True
    forced_manifest = _current_manifest(fake_r2, "rollback-run")
    assert forced_manifest["generated_cells"] == 1
    assert forced_manifest["status"] == "complete"
    assert fake_r2.upload_calls > uploads_after_first


def test_all_runs_judges_each_snapshot_independently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_root = tmp_path / "outputs"
    grown_run = _write_run_fixture(
        run_root,
        run_name="grown-run",
        planned_cells=2,
    )
    _append_cell_record(grown_run, x_index=1)
    equal_run = _write_run_fixture(
        run_root,
        run_name="equal-run",
        planned_cells=2,
    )
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "dummy-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "dummy-private")
    fake_r2 = _FakeR2Client()
    for run_name, generated_cells in (("grown-run", 1), ("equal-run", 1)):
        fake_r2.seed_object(
            "dummy-public",
            f"runs/{run_name}/view/current.json",
            json.dumps(
                {
                    "schema_version": 2,
                    "run_dir": run_name,
                    "release_id": "seed-release",
                    "status": "in_progress",
                    "generated_cells": generated_cells,
                },
                ensure_ascii=False,
            ).encode("utf-8"),
        )

    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.SupabaseWriter.from_env",
        classmethod(lambda cls, dry_run, **kwargs: _NoopSupabaseWriter()),
    )

    assert main(["--all-runs", "--run-root", str(run_root)]) == 0
    payload = _read_stdout_json(capsys)
    assert payload["mode"] == "execute"
    assert payload["force_publish"] is False

    stats_raw = payload["snapshot_stats"]
    assert isinstance(stats_raw, list)
    stats_by_run = {
        str(item["run_dir"]): item
        for item in stats_raw
        if isinstance(item, dict)
    }
    assert stats_by_run["grown-run"]["generated_cells"] == 2
    assert stats_by_run["grown-run"]["status"] == "complete"
    assert stats_by_run["equal-run"]["generated_cells"] == 1
    assert stats_by_run["equal-run"]["status"] == "in_progress"

    grown_manifest = _current_manifest(fake_r2, "grown-run")
    equal_manifest = _current_manifest(fake_r2, "equal-run")
    assert grown_manifest["release_id"] != "seed-release"
    assert grown_manifest["generated_cells"] == 2
    assert equal_manifest["release_id"] != "seed-release"
    assert equal_manifest["generated_cells"] == 1


def test_all_runs_rollback_refusal_blocks_batch_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_root = tmp_path / "outputs"
    grown_run = _write_run_fixture(
        run_root,
        run_name="grown-run",
        planned_cells=2,
    )
    _append_cell_record(grown_run, x_index=1)
    rollback_run = _write_run_fixture(
        run_root,
        run_name="rollback-run",
        planned_cells=2,
    )
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "dummy-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "dummy-private")
    fake_r2 = _FakeR2Client()
    for run_name, generated_cells in (("grown-run", 1), ("rollback-run", 2)):
        fake_r2.seed_object(
            "dummy-public",
            f"runs/{run_name}/view/current.json",
            json.dumps(
                {
                    "schema_version": 2,
                    "run_dir": run_name,
                    "release_id": "seed-release",
                    "status": "in_progress",
                    "generated_cells": generated_cells,
                },
                ensure_ascii=False,
            ).encode("utf-8"),
        )

    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.SupabaseWriter.from_env",
        classmethod(lambda cls, dry_run, **kwargs: _NoopSupabaseWriter()),
    )

    # 批次中任一评测回退：整批在写入前被拒绝，前进的那个也不得取代当前快照。
    assert main(["--all-runs", "--run-root", str(run_root)]) == 2
    payload = _read_stdout_json(capsys)
    assert payload["mode"] == "error"
    assert payload["category"] == "argument"
    assert "rollback-run" in str(payload["message"])
    assert fake_r2.upload_calls == 0
    assert _current_manifest(fake_r2, "grown-run")["release_id"] == "seed-release"
    assert _current_manifest(fake_r2, "rollback-run")["release_id"] == "seed-release"


def test_current_manifest_is_published_after_supabase_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="current-last-run")
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "dummy-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "dummy-private")
    fake_r2 = _FakeR2Client()
    writer = _CurrentOrderingSupabaseWriter(
        fake_r2=fake_r2,
        public_bucket="dummy-public",
    )

    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.SupabaseWriter.from_env",
        classmethod(lambda cls, dry_run, **kwargs: writer),
    )

    assert main(["--run-dir", str(run_dir)]) == 0
    _ = _read_stdout_json(capsys)

    assert fake_r2.uploaded_keys[-1] == (
        "dummy-public",
        "runs/current-last-run/view/current.json",
    )


def test_execute_uploads_workflow_artifact_before_db_upsert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _write_run_fixture(
        tmp_path,
        run_name="workflow-before-db-run",
        include_workflow_download=True,
    )

    monkeypatch.setenv("R2_PUBLIC_BUCKET", "dummy-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "dummy-private")

    fake_r2 = _FakeR2Client()
    fake_writer = _ArtifactAwareSupabaseWriter(
        fake_r2=fake_r2,
        public_bucket="dummy-public",
    )

    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.SupabaseWriter.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_writer),
    )

    exit_code = main(["--run-dir", str(run_dir)])
    payload = _read_stdout_json(capsys)

    assert exit_code == 0
    assert payload.get("mode") == "execute"
    assert fake_writer.calls == 1


def test_execute_reports_scanned_run_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.r2_upload import upload_planner as upload_planner_module

    monkeypatch.setattr(upload_planner_module, "_REPO_ROOT", tmp_path)
    model_dir = tmp_path / "data/models/example"
    cover_path = model_dir / "image.jpg"
    homepage_path = model_dir / "images/card.jpg"
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    homepage_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), (1, 2, 3)).save(cover_path, format="JPEG")
    Image.new("RGB", (8, 6), (4, 5, 6)).save(homepage_path, format="JPEG")

    run_dir = _write_run_fixture(tmp_path, run_name="execute-assets-run")
    run_json_path = run_dir / "run.json"
    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    assert isinstance(run_payload, dict)
    run_payload["config_path"] = "data/models/example/config.yaml"
    run_json_path.write_text(
        json.dumps(run_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setenv("R2_PUBLIC_BUCKET", "dummy-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "dummy-private")
    fake_r2 = _FakeR2Client()
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: fake_r2),
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.SupabaseWriter.from_env",
        classmethod(lambda cls, dry_run, **kwargs: _NoopSupabaseWriter()),
    )

    exit_code = main(["--run-dir", str(run_dir)])
    payload = _read_stdout_json(capsys)

    assert exit_code == 0
    assert payload.get("mode") == "execute"
    assert payload.get("asset_scans") == [
        {
            "run_dir": "execute-assets-run",
            "cover_image": "data/models/example/image.jpg",
            "homepage_images": ["data/models/example/images/card.jpg"],
        }
    ]

    uploaded_keys = [key for _, key in fake_r2.uploaded_keys]
    assert any(_sha256_file(cover_path) in key for key in uploaded_keys)
    assert any(_sha256_file(homepage_path) in key for key in uploaded_keys)


def test_execute_rejects_invalid_r2_upload_concurrency_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="invalid-upload-concurrency-run")

    monkeypatch.setenv("R2_PUBLIC_BUCKET", "dummy-public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "dummy-private")
    monkeypatch.setenv("R2_UPLOAD_CONCURRENCY", "0")

    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.R2Client.from_env",
        classmethod(lambda cls, dry_run, **kwargs: _FakeR2Client()),
    )
    monkeypatch.setattr(
        "scripts.r2_upload.upload_images_to_r2.SupabaseWriter.from_env",
        classmethod(lambda cls, dry_run, **kwargs: _NoopSupabaseWriter()),
    )

    exit_code = main(["--run-dir", str(run_dir)])
    payload = _read_stdout_json(capsys)

    assert exit_code == 3
    assert payload.get("mode") == "error"
    assert payload.get("category") == "config"
    assert payload.get("exit_code") == 3
