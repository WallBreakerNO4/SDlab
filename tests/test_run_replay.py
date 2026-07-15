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
from scripts.generation.prompt_grid import (
    Y_ARTIST_CHAIN,
    Y_POSITIVE_VALUE,
    compute_prompt_hash,
    derive_seed,
)
from scripts.generation.runner_retry import _validate_retry_failed_cells_consistency


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_run_payload(x_path: Path, y_path: Path) -> dict[str, object]:
    return {
        "x_json_path": str(x_path),
        "y_json_path": str(y_path),
        "template": "{quality}{gender}{y}",
        "quality_prompt": "masterpiece, best quality,",
        "base_seed": 123,
        "workflow_api_path": "data/workflows/demo.json",
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
        "config_path": "data/models/example/config.yaml",
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
        },
        "config_snapshot": {
            "prompts": {
                "x_path": "data/prompts/x.json",
                "y_path": "data/prompts/y.json",
                "x_sha256": _sha256_file(x_path),
                "y_sha256": _sha256_file(y_path),
            },
            "workflow": {
                "api_path": "data/workflows/demo.json",
                "api_sha256": "workflow-sha",
                "ksampler_node_id": "3",
            },
            "generation": {
                "template": "{quality}{gender}{y}",
                "quality_prompt": "masterpiece, best quality,",
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
    assert config.quality_prompt == "masterpiece, best quality,"
    assert config.generation_overrides.negative_prompt == "bad,"
    assert config.generation_overrides.append_negative_prompt == "nsfw, nipples,"
    assert config.ksampler_node_id == "3"
    assert config.anima_artist_mixer is False


def test_load_run_replay_config_reads_anima_artist_mixer(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-mixer"
    run_dir.mkdir()
    x_path = tmp_path / "x.json"
    y_path = tmp_path / "y.json"
    x_path.write_text('[{"x":1}]', encoding="utf-8")
    y_path.write_text('[{"y":"style"}]', encoding="utf-8")
    payload = _base_run_payload(x_path, y_path)
    config_snapshot = payload["config_snapshot"]
    assert isinstance(config_snapshot, dict)
    workflow = config_snapshot["workflow"]
    assert isinstance(workflow, dict)
    workflow["anima_artist_mixer"] = True
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    config = load_run_replay_config(run_dir)

    assert config.anima_artist_mixer is True


def test_retry_strict_rejects_changed_anima_artist_chain() -> None:
    x_row = {
        "gender": "1girl, ",
        "characters": "",
        "series": "",
        "rating": "safe, ",
        "general": "solo, ",
    }
    y_row = {
        "y": "(@wlop:1.2), year 2025, ",
        Y_POSITIVE_VALUE: "year 2025, ",
        Y_ARTIST_CHAIN: "1.2::@wlop",
    }
    positive_prompt = "safe, 1girl, year 2025, solo, "
    record = {
        "status": "failed",
        "artist_chain": "0.8::@wlop",
        "prompt_hash": compute_prompt_hash(positive_prompt, "1.2::@wlop"),
        "seed": derive_seed(123, 0, 0),
        "workflow_api_sha256": "workflow-hash",
    }

    with pytest.raises(ValueError, match="artist_chain"):
        _validate_retry_failed_cells_consistency(
            target_cells=[(0, 0)],
            latest_records={(0, 0): record},
            x_rows_by_index={0: x_row},
            y_rows_by_index={0: y_row},
            template="{rating}{gender}{y}{general}",
            base_seed=123,
            workflow_hash="workflow-hash",
            render_prompt=lambda template, x_value, y_value: positive_prompt,
            compute_prompt_hash=compute_prompt_hash,
            derive_seed=derive_seed,
            coerce_int_or_none=lambda value: value if isinstance(value, int) else None,
        )


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


def test_load_run_replay_config_rejects_missing_config_snapshot(
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

    with pytest.raises(ValueError, match="config_snapshot"):
        load_run_replay_config(run_dir)


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
    payload["workflow_api_path"] = str(workflow_path)
    payload["workflow_api_sha256"] = "deadbeef"
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="workflow_api_sha256 校验失败"):
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
    payload["workflow_api_path"] = str(missing_workflow_path)
    payload["workflow_api_sha256"] = "deadbeef"
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    config = load_run_replay_config(run_dir)
    assert config.workflow_api_path == str(missing_workflow_path)
