from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.r2_upload import clear_bucket


def _select_private(_prompt: str) -> str:
    return "2"


def _select_return(_prompt: str) -> str:
    return "4"


def test_clear_bucket_main_can_clear_both_buckets_from_env_target(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "public-bucket")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "private-bucket")
    monkeypatch.setenv("SDSLAB_R2_CLEAR_BUCKET_TARGET", "both")

    calls: list[str] = []

    def _fake_clear_bucket(bucket_name: str) -> int:
        calls.append(bucket_name)
        return 3 if bucket_name == "public-bucket" else 5

    monkeypatch.setattr(clear_bucket, "_clear_bucket", _fake_clear_bucket)

    exit_code = clear_bucket.main([])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == ["public-bucket", "private-bucket"]
    assert "完成: 已清空桶 public-bucket，删除对象数 3" in output
    assert "完成: 已清空桶 private-bucket，删除对象数 5" in output
    assert "汇总: 已清空 2 个桶，总删除对象数 8" in output


def test_clear_bucket_main_prompts_with_configured_bucket_options(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "public-bucket")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "private-bucket")
    monkeypatch.delenv("SDSLAB_R2_CLEAR_BUCKET_TARGET", raising=False)
    monkeypatch.delenv("SDSLAB_R2_CLEAR_BUCKET_NAME", raising=False)

    calls: list[str] = []

    def _fake_clear_bucket(bucket_name: str) -> int:
        calls.append(bucket_name)
        return 2

    monkeypatch.setattr(clear_bucket, "_clear_bucket", _fake_clear_bucket)
    monkeypatch.setattr("builtins.input", _select_private)

    exit_code = clear_bucket.main([])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == ["private-bucket"]
    assert "1) 清空 R2_PUBLIC_BUCKET (public-bucket)" in output
    assert "2) 清空 R2_PRIVATE_BUCKET (private-bucket)" in output
    assert "3) 清空二者" in output
    assert "4) 返回" in output


def test_clear_bucket_main_can_return_without_deleting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("R2_PUBLIC_BUCKET", "public-bucket")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "private-bucket")
    monkeypatch.delenv("SDSLAB_R2_CLEAR_BUCKET_TARGET", raising=False)
    monkeypatch.delenv("SDSLAB_R2_CLEAR_BUCKET_NAME", raising=False)

    def _unexpected_clear_bucket(_bucket_name: str) -> int:
        raise AssertionError("不应在返回路径中执行删除")

    monkeypatch.setattr(clear_bucket, "_clear_bucket", _unexpected_clear_bucket)
    monkeypatch.setattr("builtins.input", _select_return)

    exit_code = clear_bucket.main([])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "已取消清空 R2 桶。" in output
