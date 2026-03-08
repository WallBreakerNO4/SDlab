# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generation.run_replay import load_run_replay_config


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_run_payload(x_path: Path, y_path: Path) -> dict[str, object]:
    return {
        "x_json_path": str(x_path),
        "y_json_path": str(y_path),
        "template": "{gender}{y}{quality}",
        "base_seed": 123,
        "workflow_json_path": "data/workflows/demo.json",
        "x_json_sha256": _sha256_file(x_path),
        "y_json_sha256": _sha256_file(y_path),
        "generation_overrides": {
            "negative_prompt": "bad,",
            "append_negative_prompt": "nsfw, nipples,",
            "width": 832,
            "height": 1216,
            "batch_size": 1,
            "steps": 28,
            "cfg": 5.5,
            "denoise": 1.0,
            "sampler_name": "euler",
            "scheduler": "normal",
        },
        "selection": {
            "x_indexes": [0, 2],
            "y_indexes": [1],
        },
        "config_schema_version": "image-run-config/v1",
        "config_path": "data/runs/example.yaml",
        "config_sha256": "config-sha",
        "model": {
            "key": "nai-4-full",
            "name": "NAI 4 Full",
            "family": "novelai",
            "links": {
                "homepage": "https://example.com/model",
                "huggingface": None,
                "civitai": None,
            },
            "description": {"zh": "测试模型", "en": "Test model"},
            "tags": ["anime", "full"],
        },
        "config_snapshot": {
            "prompts": {
                "x_path": "data/prompts/x.json",
                "y_path": "data/prompts/y.json",
                "x_sha256": _sha256_file(x_path),
                "y_sha256": _sha256_file(y_path),
            },
            "workflow": {
                "path": "data/workflows/demo.json",
                "sha256": "workflow-sha",
                "ksampler_node_id": "3",
            },
            "generation": {
                "template": "{gender}{y}{quality}",
                "base_seed": 123,
                "negative_prompt": "bad,",
                "append_negative_prompt": "nsfw, nipples,",
                "width": 832,
                "height": 1216,
                "batch_size": 1,
                "steps": 28,
                "cfg": 5.5,
                "denoise": 1.0,
                "sampler_name": "euler",
                "scheduler": "normal",
            },
            "selection": {
                "x_limit": None,
                "y_limit": None,
                "x_indexes": [0, 2],
                "y_indexes": [1],
            },
        },
    }


def test_load_run_replay_config_reads_optional_new_snapshot_fields(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    x_path = tmp_path / "x.json"
    y_path = tmp_path / "y.json"
    x_path.write_text('[{"x":1}]', encoding="utf-8")
    y_path.write_text('[{"y":"style"}]', encoding="utf-8")

    payload = _base_run_payload(x_path, y_path)
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    config = load_run_replay_config(run_dir)

    assert config.x_json_path == x_path
    assert config.y_json_path == y_path
    assert config.generation_overrides.negative_prompt == "bad,"
    assert config.generation_overrides.append_negative_prompt == "nsfw, nipples,"
    assert config.ksampler_node_id == "3"


def test_load_run_replay_config_allows_missing_append_negative_prompt(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-missing-append"
    run_dir.mkdir()
    x_path = tmp_path / "x.json"
    y_path = tmp_path / "y.json"
    x_path.write_text('[{"x":1}]', encoding="utf-8")
    y_path.write_text('[{"y":"style"}]', encoding="utf-8")

    payload = _base_run_payload(x_path, y_path)
    generation_overrides = payload["generation_overrides"]
    assert isinstance(generation_overrides, dict)
    generation_overrides.pop("append_negative_prompt")
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    config = load_run_replay_config(run_dir)
    assert config.generation_overrides.append_negative_prompt is None


def test_load_run_replay_config_allows_missing_ksampler_snapshot(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-missing-ksampler"
    run_dir.mkdir()
    x_path = tmp_path / "x.json"
    y_path = tmp_path / "y.json"
    x_path.write_text('[{"x":1}]', encoding="utf-8")
    y_path.write_text('[{"y":"style"}]', encoding="utf-8")

    payload = _base_run_payload(x_path, y_path)
    config_snapshot = payload["config_snapshot"]
    assert isinstance(config_snapshot, dict)
    workflow_snapshot = config_snapshot["workflow"]
    assert isinstance(workflow_snapshot, dict)
    workflow_snapshot.pop("ksampler_node_id")
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    config = load_run_replay_config(run_dir)
    assert config.ksampler_node_id is None


def test_load_run_replay_config_allows_legacy_payload_without_config_snapshot(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-legacy"
    run_dir.mkdir()
    x_path = tmp_path / "x.json"
    y_path = tmp_path / "y.json"
    x_path.write_text('[{"x":1}]', encoding="utf-8")
    y_path.write_text('[{"y":"style"}]', encoding="utf-8")

    payload = _base_run_payload(x_path, y_path)
    payload.pop("config_snapshot")
    generation_overrides = payload["generation_overrides"]
    assert isinstance(generation_overrides, dict)
    generation_overrides.pop("append_negative_prompt")
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    config = load_run_replay_config(run_dir)
    assert config.generation_overrides.append_negative_prompt is None
    assert config.ksampler_node_id is None


def test_load_run_replay_config_sha_mismatch(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-sha"
    run_dir.mkdir()
    x_path = tmp_path / "x.json"
    y_path = tmp_path / "y.json"
    x_path.write_text('[{"x":1}]', encoding="utf-8")
    y_path.write_text('[{"y":"style"}]', encoding="utf-8")

    payload = _base_run_payload(x_path, y_path)
    payload["x_json_sha256"] = "deadbeef"
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="x_json_sha256 校验失败"):
        load_run_replay_config(run_dir)


def test_load_run_replay_config_workflow_sha_mismatch_when_workflow_readable(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-workflow-sha"
    run_dir.mkdir()
    x_path = tmp_path / "x.json"
    y_path = tmp_path / "y.json"
    workflow_path = tmp_path / "workflow.json"
    x_path.write_text('[{"x":1}]', encoding="utf-8")
    y_path.write_text('[{"y":"style"}]', encoding="utf-8")
    workflow_path.write_text('{"3":{"inputs":{}}}', encoding="utf-8")

    payload = _base_run_payload(x_path, y_path)
    payload["workflow_json_path"] = str(workflow_path)
    payload["workflow_json_sha256"] = "deadbeef"
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="workflow_json_sha256 校验失败"):
        load_run_replay_config(run_dir)


def test_load_run_replay_config_allows_workflow_sha_when_workflow_unreadable(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-workflow-missing"
    run_dir.mkdir()
    x_path = tmp_path / "x.json"
    y_path = tmp_path / "y.json"
    missing_workflow_path = tmp_path / "missing-workflow.json"
    x_path.write_text('[{"x":1}]', encoding="utf-8")
    y_path.write_text('[{"y":"style"}]', encoding="utf-8")

    payload = _base_run_payload(x_path, y_path)
    payload["workflow_json_path"] = str(missing_workflow_path)
    payload["workflow_json_sha256"] = "deadbeef"
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    config = load_run_replay_config(run_dir)
    assert config.workflow_json_path == str(missing_workflow_path)
