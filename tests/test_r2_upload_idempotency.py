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
    root: Path, *, run_name: str, include_workflow_download: bool = False
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


class _FakeR2Client:
    def __init__(self) -> None:
        self._objects: set[tuple[str, str]] = set()
        self._object_bodies: dict[tuple[str, str], bytes] = {}
        self.upload_calls: int = 0
        self.uploaded_keys: list[tuple[str, str]] = []

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


def test_changed_release_requires_force_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="force-publish-run")
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
    uploads_after_first = fake_r2.upload_calls

    metadata_path = run_dir / "metadata.jsonl"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["positive_prompt"] = "changed prompt"
    metadata["prompt_hash"] = "changed-hash"
    metadata_path.write_text(json.dumps(metadata) + "\n", encoding="utf-8")

    assert main(["--run-dir", str(run_dir)]) == 2
    rejected_payload = _read_stdout_json(capsys)
    assert rejected_payload["category"] == "argument"
    assert fake_r2.upload_calls == uploads_after_first

    assert main(["-F", "--run-dir", str(run_dir)]) == 0
    force_payload = _read_stdout_json(capsys)
    assert force_payload["force_publish"] is True
    assert fake_r2.upload_calls > uploads_after_first


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
