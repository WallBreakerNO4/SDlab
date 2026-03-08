# pyright: basic, reportMissingImports=false, reportUnusedCallResult=false, reportAttributeAccessIssue=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import hashlib
import importlib
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEPRECATED_BUSINESS_ENV_KEYS = [
    "COMFYUI_X_JSON",
    "COMFYUI_Y_JSON",
    "COMFYUI_TEMPLATE",
    "COMFYUI_BASE_SEED",
    "COMFYUI_WORKFLOW_JSON",
    "COMFYUI_KSAMPLER_NODE_ID",
    "COMFYUI_X_LIMIT",
    "COMFYUI_Y_LIMIT",
    "COMFYUI_X_INDEXES",
    "COMFYUI_Y_INDEXES",
    "COMFYUI_NEGATIVE_PROMPT",
    "COMFYUI_APPEND_NEGATIVE_PROMPT",
    "COMFYUI_WIDTH",
    "COMFYUI_HEIGHT",
    "COMFYUI_BATCH_SIZE",
    "COMFYUI_STEPS",
    "COMFYUI_CFG",
    "COMFYUI_DENOISE",
    "COMFYUI_SAMPLER_NAME",
    "COMFYUI_SCHEDULER",
]


def _install_runner_config_stub() -> None:
    module = types.ModuleType("scripts.generation.runner_config")

    def load_runner_config(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        raise AssertionError("测试需显式 monkeypatch load_runner_config")

    setattr(module, "load_runner_config", load_runner_config)
    sys.modules["scripts.generation.runner_config"] = module


def _import_runner_module():
    _install_runner_config_stub()
    _ = sys.modules.pop("scripts.generation.comfyui_part1_generate", None)
    return importlib.import_module("scripts.generation.comfyui_part1_generate")


def _clear_deprecated_business_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in DEPRECATED_BUSINESS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _write_json_inputs(
    tmp_path: Path,
    *,
    x_info_type: str = "sfw",
) -> tuple[Path, Path]:
    x_path = tmp_path / "x.json"
    y_path = tmp_path / "y.json"
    x_payload = {
        "schema": "",
        "items": [
            {
                "tags": {
                    "gender": [{"text": "1girl", "weight": 1.0}],
                    "characters": [{"text": "amiya", "weight": 1.0}],
                    "series": [{"text": "arknights", "weight": 1.0}],
                    "rating": [{"text": "safe", "weight": 1.0}],
                    "general": [{"text": "solo", "weight": 1.0}],
                    "quality": [{"text": "masterpiece", "weight": 1.0}],
                },
                "info": {"index": 0, "type": x_info_type},
                "description": {"zh": "示例模型", "en": "Example model"},
            }
        ],
    }
    y_payload = {
        "schema": "prompt-y-table/v2",
        "items": [
            {
                "tags": [{"text": "artist-a", "weight": 1.0}],
                "info": {"index": 0, "type": "artists"},
            }
        ],
    }
    x_path.write_text(
        json.dumps(x_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    y_path.write_text(
        json.dumps(y_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return x_path, y_path


def _read_valid_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        assert isinstance(payload, dict)
        records.append(payload)
    return records


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_runner_config(
    *,
    config_path: Path,
    x_path: Path,
    y_path: Path,
    append_negative_prompt: str | None,
) -> SimpleNamespace:
    workflow_path = config_path.parent / "workflow.json"
    workflow_path.write_text('{"3": {"class_type": "KSampler"}}\n', encoding="utf-8")
    return SimpleNamespace(
        schema_version="image-run-config/v1",
        config_path="data/runs/example.yaml",
        config_sha256=_sha256_file(config_path),
        model=SimpleNamespace(
            key="nai-4-full",
            name="NAI 4 Full",
            family="novelai",
            links={
                "homepage": "https://example.com/model",
                "huggingface": None,
                "civitai": None,
            },
            description={"zh": "测试模型", "en": "Test model"},
            tags=["anime", "full"],
        ),
        prompts=SimpleNamespace(
            x=SimpleNamespace(
                path=str(x_path),
                sha256=_sha256_file(x_path),
                repo_relative_path="data/prompts/x.json",
            ),
            y=SimpleNamespace(
                path=str(y_path),
                sha256=_sha256_file(y_path),
                repo_relative_path="data/prompts/y.json",
            ),
        ),
        workflow=SimpleNamespace(
            path=str(workflow_path),
            sha256=_sha256_file(workflow_path),
            repo_relative_path="data/workflows/example.json",
            ksampler_node_id="3",
        ),
        generation=SimpleNamespace(
            template="{gender}{characters}{series}{rating}{y}{general}{quality}",
            base_seed=123,
            negative_prompt="neg,",
            append_negative_prompt=append_negative_prompt,
            width=832,
            height=1216,
            batch_size=1,
            steps=28,
            cfg=5.5,
            denoise=1.0,
            sampler_name="euler",
            scheduler="normal",
        ),
        selection=SimpleNamespace(
            x_limit=1,
            y_limit=1,
            x_indexes=[0],
            y_indexes=[0],
        ),
    )


def test_cli_help_exposes_config_runtime_flags_only() -> None:
    runner = _import_runner_module()
    help_text = runner.build_parser().format_help()

    for flag in [
        "--config",
        "--run-dir",
        "--dry-run",
        "--retry-failed",
        "--retry-incomplete",
        "--retry-error-code",
        "--base-url",
        "--request-timeout-s",
        "--job-timeout-s",
        "--concurrency",
        "--client-id",
    ]:
        assert flag in help_text

    for removed_flag in [
        "--x-json",
        "--y-json",
        "--template",
        "--base-seed",
        "--workflow-json",
        "--negative-prompt",
        "--width",
        "--height",
    ]:
        assert removed_flag not in help_text


def test_dry_run_with_config_writes_run_json_snapshot_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _import_runner_module()
    _clear_deprecated_business_env(monkeypatch)
    x_path, y_path = _write_json_inputs(tmp_path)
    config_path = tmp_path / "example.yaml"
    config_path.write_text("schema_version: image-run-config/v1\n", encoding="utf-8")
    run_dir = tmp_path / "run-dry"
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        runner,
        "load_runner_config",
        lambda path, repo_root: _fake_runner_config(
            config_path=config_path,
            x_path=x_path,
            y_path=y_path,
            append_negative_prompt="app,",
        ),
    )

    exit_code = runner.main(
        ["--dry-run", "--config", str(config_path), "--run-dir", str(run_dir)]
    )

    assert exit_code == 0
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["x_json_path"] == str(x_path)
    assert run_payload["y_json_path"] == str(y_path)
    assert (
        run_payload["template"]
        == "{gender}{characters}{series}{rating}{y}{general}{quality}"
    )
    assert run_payload["base_seed"] == 123
    assert run_payload["generation_overrides"]["negative_prompt"] == "neg,"
    assert run_payload["generation_overrides"]["append_negative_prompt"] == "app,"
    assert run_payload["config_schema_version"] == "image-run-config/v1"
    assert run_payload["config_path"] == "data/runs/example.yaml"
    assert run_payload["config_sha256"] == _sha256_file(config_path)
    assert run_payload["model"] == {
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
    }
    assert run_payload["config_snapshot"] == {
        "prompts": {
            "x_path": "data/prompts/x.json",
            "y_path": "data/prompts/y.json",
            "x_sha256": _sha256_file(x_path),
            "y_sha256": _sha256_file(y_path),
        },
        "workflow": {
            "path": "data/workflows/example.json",
            "sha256": run_payload["config_snapshot"]["workflow"]["sha256"],
            "ksampler_node_id": "3",
        },
        "generation": {
            "template": "{gender}{characters}{series}{rating}{y}{general}{quality}",
            "base_seed": 123,
            "negative_prompt": "neg,",
            "append_negative_prompt": "app,",
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
            "x_limit": 1,
            "y_limit": 1,
            "x_indexes": [0],
            "y_indexes": [0],
        },
    }

    metadata_records = _read_valid_jsonl(run_dir / "metadata.jsonl")
    assert len(metadata_records) == 1
    assert metadata_records[0]["status"] == "skipped"


def test_dry_run_uses_config_append_negative_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _import_runner_module()
    _clear_deprecated_business_env(monkeypatch)
    x_path, y_path = _write_json_inputs(tmp_path, x_info_type="normal")
    config_path = tmp_path / "example.yaml"
    config_path.write_text("schema_version: image-run-config/v1\n", encoding="utf-8")
    run_dir = tmp_path / "run-append-negative"
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        runner,
        "load_runner_config",
        lambda path, repo_root: _fake_runner_config(
            config_path=config_path,
            x_path=x_path,
            y_path=y_path,
            append_negative_prompt="app,",
        ),
    )

    exit_code = runner.main(
        ["--dry-run", "--config", str(config_path), "--run-dir", str(run_dir)]
    )

    assert exit_code == 0
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["generation_overrides"]["append_negative_prompt"] == "app,"

    metadata_records = _read_valid_jsonl(run_dir / "metadata.jsonl")
    assert len(metadata_records) == 1
    generation_params = metadata_records[0].get("generation_params")
    assert isinstance(generation_params, dict)
    assert generation_params["negative_prompt"] == "neg, app,"


def test_run_dry_run_ignores_env_append_negative_prompt_in_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _import_runner_module()
    _clear_deprecated_business_env(monkeypatch)
    x_path, y_path = _write_json_inputs(tmp_path, x_info_type="normal")
    run_dir = tmp_path / "run-ignore-env-append"
    run_dir.mkdir()
    monkeypatch.setenv("COMFYUI_APPEND_NEGATIVE_PROMPT", "from-env,")

    args = SimpleNamespace(
        config=None,
        dry_run=True,
        retry_failed=False,
        retry_incomplete=False,
        retry_error_code=None,
        run_dir=str(run_dir),
        client_id="test-client",
        base_url="http://127.0.0.1:8188",
        request_timeout_s=1.0,
        job_timeout_s=2.0,
        concurrency=1,
        x_json=str(x_path),
        y_json=str(y_path),
        template="{gender}{characters}{series}{rating}{y}{general}{quality}",
        base_seed=123,
        workflow_json=None,
        ksampler_node_id="3",
        negative_prompt="neg,",
        append_negative_prompt="app,",
        width=832,
        height=1216,
        batch_size=1,
        steps=28,
        cfg=5.5,
        denoise=1.0,
        sampler_name="euler",
        scheduler="normal",
        x_limit=1,
        y_limit=1,
        x_indexes="0",
        y_indexes="0",
    )

    exit_code = runner.run(args)

    assert exit_code == 0
    metadata_records = _read_valid_jsonl(run_dir / "metadata.jsonl")
    assert len(metadata_records) == 1
    generation_params = metadata_records[0].get("generation_params")
    assert isinstance(generation_params, dict)
    assert generation_params["negative_prompt"] == "neg, app,"


def test_dry_run_run_json_snapshot_stays_compact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _import_runner_module()
    _clear_deprecated_business_env(monkeypatch)
    x_path, y_path = _write_json_inputs(tmp_path)
    config_path = tmp_path / "example.yaml"
    config_path.write_text("schema_version: image-run-config/v1\n", encoding="utf-8")
    run_dir = tmp_path / "run-compact"
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        runner,
        "load_runner_config",
        lambda path, repo_root: _fake_runner_config(
            config_path=config_path,
            x_path=x_path,
            y_path=y_path,
            append_negative_prompt=None,
        ),
    )

    exit_code = runner.main(
        ["--dry-run", "--config", str(config_path), "--run-dir", str(run_dir)]
    )

    assert exit_code == 0
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    snapshot = run_payload["config_snapshot"]
    assert "items" not in snapshot["prompts"]
    assert "raw" not in snapshot["prompts"]
    assert "json" not in snapshot["workflow"]
    assert "workflow" not in run_payload["model"]
    assert "prompt_items" not in run_payload["model"]
