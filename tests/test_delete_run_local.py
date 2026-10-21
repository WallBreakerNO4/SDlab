# pyright: basic, reportMissingImports=false

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.r2_upload.delete_run import build_parser, main


class _FakeS3Client:
    def __init__(self) -> None:
        self.list_calls: list[dict[str, object]] = []
        self.delete_calls: list[dict[str, object]] = []

    def list_objects_v2(self, **request: object) -> dict[str, object]:
        self.list_calls.append(request)
        return {
            "Contents": [{"Key": "runs/run-a/display_webp.png"}],
            "IsTruncated": False,
        }

    def delete_objects(self, **request: object) -> dict[str, object]:
        self.delete_calls.append(request)
        return {"Deleted": [{"Key": "runs/run-a/display_webp.png"}]}


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def request_json(
        self,
        *,
        method: str,
        table_name: str,
        query_params: object,
        body: object,
        extra_headers: object,
    ) -> list[dict[str, object]]:
        self.calls.append(
            {
                "method": method,
                "table": table_name,
                "query_params": query_params,
            }
        )
        if method == "GET":
            return [{"id": "run-id-a"}]
        if method == "DELETE":
            return [{"id": "run-id-a"}]
        return []


@pytest.fixture(autouse=True)
def _isolated_database_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "local-service-key")


def _stub_env_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.r2_upload.delete_run.load_env_files",
        lambda **kwargs: None,
    )


def test_build_parser_accepts_local_flag_with_existing_options() -> None:
    args = build_parser().parse_args(
        ["--local", "--run-dir", "run-a", "--dry-run", "--yes"]
    )

    assert args.local is True
    assert args.run_dir == "run-a"
    assert args.dry_run is True
    assert args.yes is True


def test_main_local_deletes_database_rows_and_never_touches_r2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_env_loading(monkeypatch)
    s3 = _FakeS3Client()
    supabase = _FakeSupabaseClient()

    exit_code = main(
        ["--local", "--run-dir", "run-a", "--yes"],
        s3_client_factory=lambda: s3,
        supabase_client_factory=lambda: supabase,
    )

    assert exit_code == 0
    # 最关键的安全断言：本地开发阶段零 R2 调用、零 R2 删除
    assert s3.list_calls == []
    assert s3.delete_calls == []
    assert [call["method"] for call in supabase.calls] == ["GET", "DELETE"]
    assert all(call["table"] == "runs" for call in supabase.calls)

    output = capsys.readouterr().out
    assert "已跳过 R2 对象删除" in output
    assert "已删除 1 条 runs 记录" in output


def test_main_local_dry_run_also_skips_r2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_env_loading(monkeypatch)
    s3 = _FakeS3Client()
    supabase = _FakeSupabaseClient()

    exit_code = main(
        ["--local", "--run-dir", "run-a", "--dry-run"],
        s3_client_factory=lambda: s3,
        supabase_client_factory=lambda: supabase,
    )

    assert exit_code == 0
    assert s3.list_calls == []
    assert s3.delete_calls == []
    assert [call["method"] for call in supabase.calls] == ["GET"]
    assert "已跳过 R2 对象删除" in capsys.readouterr().out


def test_main_default_path_still_deletes_r2_and_database_rows(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "public-bucket")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "private-bucket")
    s3 = _FakeS3Client()
    supabase = _FakeSupabaseClient()

    exit_code = main(
        ["--run-dir", "run-a", "--yes"],
        s3_client_factory=lambda: s3,
        supabase_client_factory=lambda: supabase,
    )

    assert exit_code == 0
    assert len(s3.list_calls) == 4  # 预览 + 实际删除，各两个 bucket
    assert len(s3.delete_calls) == 2
    assert [call["method"] for call in supabase.calls] == ["GET", "DELETE"]
    assert "已跳过 R2 对象删除" not in capsys.readouterr().out


def test_main_local_without_env_file_reports_config_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "scripts.env_loading.find_dotenv",
        lambda *args, **kwargs: "",
    )

    exit_code = main(["--local", "--run-dir", "run-a"])

    assert exit_code == 2
    assert ".env.local-db" in capsys.readouterr().err
