# pyright: basic, reportMissingImports=false, reportUnusedCallResult=false

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generation.comfyui_part1_generate import build_parser, main


def test_cli_help_contains_retry_flags() -> None:
    """验证帮助文本包含重试相关的所有新 flags"""
    help_text = build_parser().format_help()

    for flag in [
        "--retry-failed",
        "--retry-incomplete",
        "--retry-error-code",
    ]:
        assert flag in help_text


def test_retry_failed_requires_run_dir(capsys: pytest.CaptureFixture[str]) -> None:
    """--retry-failed 必须提供 --run-dir，否则 exit 2"""
    exit_code = main(["--retry-failed", "--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "retry 模式必须提供 --run-dir" in captured.err


def test_retry_failed_requires_existing_run_dir(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--retry-failed --run-dir 指向不存在的目录时 exit 2"""
    non_existent = tmp_path / "does-not-exist"

    exit_code = main(["--retry-failed", "--dry-run", "--run-dir", str(non_existent)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "不存在或不是目录" in captured.err
    assert str(non_existent) in captured.err


def test_retry_error_code_requires_retry_mode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--retry-error-code 未与 --retry-failed/--retry-incomplete 一起使用时 exit 2"""
    run_dir = tmp_path / "mock-run"
    run_dir.mkdir()

    exit_code = main(
        [
            "--dry-run",
            "--run-dir",
            str(run_dir),
            "--retry-error-code",
            "network_timeout",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "仅可与 --retry-failed/--retry-incomplete 一起使用" in captured.err


def test_retry_error_code_empty_string(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--retry-error-code 为空字符串时 exit 2"""
    run_dir = tmp_path / "mock-run"
    run_dir.mkdir()

    exit_code = main(
        [
            "--retry-failed",
            "--dry-run",
            "--run-dir",
            str(run_dir),
            "--retry-error-code",
            "",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--retry-error-code 不能为空" in captured.err


def test_retry_failed_accepts_valid_run_dir_with_dry_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--retry-failed --dry-run 与有效的 run_dir 组合时应该能够正常解析参数（不需要完整的 run.json）"""
    run_dir = tmp_path / "mock-run"
    run_dir.mkdir()

    exit_code = main(["--retry-failed", "--dry-run", "--run-dir", str(run_dir)])
    captured = capsys.readouterr()

    # 预期会报错因为需要 run.json，但这是参数校验通过后的错误
    # 我们只验证参数解析阶段（即 --run-dir 校验）通过了
    assert exit_code == 2
    # 错误应该不是关于 --run-dir 的
    assert "不存在或不是目录" not in captured.err
    assert "retry 模式必须提供 --run-dir" not in captured.err


def test_retry_incomplete_requires_run_dir(capsys: pytest.CaptureFixture[str]) -> None:
    """--retry-incomplete 必须提供 --run-dir，否则 exit 2"""
    exit_code = main(["--retry-incomplete", "--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "retry 模式必须提供 --run-dir" in captured.err


def test_retry_error_code_with_retry_incomplete_requires_run_dir(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--retry-error-code 与 --retry-incomplete 组合时也必须提供 --run-dir"""
    exit_code = main(["--retry-incomplete", "--retry-error-code", "timeout"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "retry 模式必须提供 --run-dir" in captured.err


def test_retry_failed_without_run_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """retry 模式 runDir 缺 run.json 时应 exit 2，stderr 含 'run.json 不存在'"""
    run_dir = tmp_path / "mock-run"
    run_dir.mkdir()

    exit_code = main(["--retry-failed", "--dry-run", "--run-dir", str(run_dir)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "run.json 不存在" in captured.err


def test_retry_failed_with_sha256_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """retry 模式 run.json 中 x_json_sha256 错误时应 exit 2，stderr 含 'x_json_sha256 校验失败'"""
    run_dir = tmp_path / "mock-run"
    run_dir.mkdir()

    # 创建一个有效的 x.json 文件（用于计算正确的 sha256）
    x_json = run_dir / "x.json"
    x_json.write_text('{"schema":"","items":[]}', encoding="utf-8")

    # 创建一个有效的 y.json 文件
    y_json = run_dir / "y.json"
    y_json.write_text('{"schema":"prompt-y-table/v3","items":[]}', encoding="utf-8")

    # 构造 run.json，但 x_json_sha256 故意错误
    run_json = {
        "x_json_path": str(x_json),
        "y_json_path": str(y_json),
        "template": "",
        "quality_prompt": "masterpiece,",
        "base_seed": 123,
        "workflow_api_path": None,
        "x_json_sha256": "wrong_sha256" * 10,  # 故意错误的 sha256
        "y_json_sha256": "wrong_sha256" * 10,
        "config_snapshot": {
            "workflow": {
                "api_path": "data/models/example/api.json",
                "api_sha256": "wf-hash",
                "download_path": "data/models/example/workflow.json",
                "download_sha256": "download-sha",
                "ksampler_node_id": None,
            }
        },
        "generation_overrides": {
            "negative_prompt": None,
            "width": None,
            "height": None,
            "batch_size": None,
            "steps": None,
            "cfg": None,
            "denoise": None,
            "sampler_name": None,
            "scheduler": None,
        },
        "selection": {
            "x_indexes": [0],
            "y_indexes": [0],
        },
    }

    (run_dir / "run.json").write_text(
        json.dumps(run_json, ensure_ascii=False), encoding="utf-8"
    )

    exit_code = main(["--retry-failed", "--dry-run", "--run-dir", str(run_dir)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "x_json_sha256 校验失败" in captured.err


def test_retry_failed_with_malformed_metadata_jsonl(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """retry 模式 metadata.jsonl 含坏 JSON 行时应 exit 2，stderr 含 'metadata.jsonl:' 与 'malformed JSON'"""
    import hashlib

    run_dir = tmp_path / "mock-run"
    run_dir.mkdir()

    # 创建有效的 x.json 和 y.json 文件
    x_json = run_dir / "x.json"
    x_json.write_text(
        '{"schema":"","items":[{"tags":[],"info":{"index":0}}]}', encoding="utf-8"
    )

    y_json = run_dir / "y.json"
    y_json.write_text(
        '{"schema":"prompt-y-table/v3","items":[{"tags":[],"info":{"index":0}}]}',
        encoding="utf-8",
    )

    # 计算正确的 sha256
    def sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    # 构造完整的 run.json（所有字段正确）
    run_json = {
        "x_json_path": str(x_json),
        "y_json_path": str(y_json),
        "template": "",
        "quality_prompt": "masterpiece,",
        "base_seed": 123,
        "workflow_api_path": None,
        "x_json_sha256": sha256_file(x_json),
        "y_json_sha256": sha256_file(y_json),
        "config_snapshot": {
            "workflow": {
                "api_path": "data/models/example/api.json",
                "api_sha256": "wf-hash",
                "download_path": "data/models/example/workflow.json",
                "download_sha256": "download-sha",
                "ksampler_node_id": None,
            }
        },
        "generation_overrides": {
            "negative_prompt": None,
            "width": None,
            "height": None,
            "batch_size": None,
            "steps": None,
            "cfg": None,
            "denoise": None,
            "sampler_name": None,
            "scheduler": None,
        },
        "selection": {
            "x_indexes": [0],
            "y_indexes": [0],
        },
    }

    (run_dir / "run.json").write_text(
        json.dumps(run_json, ensure_ascii=False), encoding="utf-8"
    )

    # 构造 metadata.jsonl，包含一行坏的 JSON
    metadata_jsonl = run_dir / "metadata.jsonl"
    metadata_jsonl.write_text('{"x_index":0,"y_index":0}\n{', encoding="utf-8")

    exit_code = main(["--retry-failed", "--dry-run", "--run-dir", str(run_dir)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "metadata.jsonl:" in captured.err
    assert "malformed JSON" in captured.err
