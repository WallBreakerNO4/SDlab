# pyright: basic, reportMissingImports=false

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.upload_images_to_r2 import main


def _write_run_fixture(root: Path, *, run_name: str) -> Path:
    run_dir = root / run_name
    images_dir = run_dir / "images"
    images_dir.mkdir(parents=True)

    image_path = images_dir / "x0-y0.png"
    Image.new("RGB", (8, 6), (23, 45, 67)).save(image_path, format="PNG")

    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "test-run-id",
                "run_dir": str(run_dir),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "metadata.jsonl").write_text(
        json.dumps(
            {
                "status": "success",
                "x_index": 0,
                "y_index": 0,
                "local_image_path": "images/x0-y0.png",
                "category": "normal",
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
        self.upload_calls: int = 0
        self.uploaded_keys: list[tuple[str, str]] = []

    def head_exists(self, bucket_name: str, key: str, *, bucket_scope: str) -> bool:
        _ = bucket_scope
        return (bucket_name, key) in self._objects

    def upload(self, plan: object) -> None:
        bucket_name = str(getattr(plan, "bucket_name"))
        key = str(getattr(plan, "key"))
        self.upload_calls += 1
        self.uploaded_keys.append((bucket_name, key))
        self._objects.add((bucket_name, key))


class _FakeSupabaseError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("simulated db failure")
        self.category = "remote"


class _FakeSupabaseWriter:
    def __init__(self) -> None:
        self.calls: int = 0

    def upsert_upload_index(self, payload: dict[str, object]) -> None:
        _ = payload
        self.calls += 1
        if self.calls == 1:
            raise _FakeSupabaseError()


def _read_stdout_json(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    output = capsys.readouterr().out.strip()
    assert output
    lines = [line for line in output.splitlines() if line.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def test_rerun_recovers_db_after_partial_failure_without_reupload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _write_run_fixture(tmp_path, run_name="run-20260221T150000Z")

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
    assert fake_r2.upload_calls == uploaded_after_first + 2

    key_counts: dict[tuple[str, str], int] = {}
    for object_ref in fake_r2.uploaded_keys:
        key_counts[object_ref] = key_counts.get(object_ref, 0) + 1
    assert all(count == 1 for count in key_counts.values())
