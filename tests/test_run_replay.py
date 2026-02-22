# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generation.run_replay import load_run_replay_config


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


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
    }


def test_load_run_replay_config_happy_path(tmp_path: Path) -> None:
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
    assert config.template == "{gender}{y}{quality}"
    assert config.base_seed == 123
    assert config.workflow_json_path == "data/workflows/demo.json"
    assert config.x_json_sha256 == _sha256_file(x_path)
    assert config.y_json_sha256 == _sha256_file(y_path)
    assert config.selection.x_indexes == [0, 2]
    assert config.selection.y_indexes == [1]
    assert config.generation_overrides.negative_prompt == "bad,"
    assert config.generation_overrides.width == 832
    assert config.generation_overrides.cfg == 5.5


def test_load_run_replay_config_missing_run_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-missing"
    run_dir.mkdir()

    with pytest.raises(ValueError, match="run.json 不存在"):
        load_run_replay_config(run_dir)


def test_load_run_replay_config_invalid_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-invalid"
    run_dir.mkdir()
    (run_dir / "run.json").write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="run.json 不是合法 JSON"):
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


def test_load_run_replay_config_type_error_on_selection_indexes(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-type"
    run_dir.mkdir()
    x_path = tmp_path / "x.json"
    y_path = tmp_path / "y.json"
    x_path.write_text('[{"x":1}]', encoding="utf-8")
    y_path.write_text('[{"y":"style"}]', encoding="utf-8")

    payload = _base_run_payload(x_path, y_path)
    selection = payload["selection"]
    assert isinstance(selection, dict)
    selection["x_indexes"] = [0, "1"]
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="selection.x_indexes"):
        load_run_replay_config(run_dir)


def test_load_run_replay_config_missing_required_field(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-missing-field"
    run_dir.mkdir()
    x_path = tmp_path / "x.json"
    y_path = tmp_path / "y.json"
    x_path.write_text('[{"x":1}]', encoding="utf-8")
    y_path.write_text('[{"y":"style"}]', encoding="utf-8")

    payload = _base_run_payload(x_path, y_path)
    payload.pop("template")
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="缺少字段: template"):
        load_run_replay_config(run_dir)
