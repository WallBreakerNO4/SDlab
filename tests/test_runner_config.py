# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false, reportUnusedCallResult=false, reportUnknownVariableType=false

import hashlib
import importlib
import json
import sys
import types
from pathlib import Path
from typing import Protocol, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _PromptRef(Protocol):
    path: str
    repo_relative_path: str
    sha256: str


class _PromptsConfig(Protocol):
    x: _PromptRef
    y: _PromptRef


class _WorkflowConfig(Protocol):
    path: str
    repo_relative_path: str
    sha256: str


class _ModelConfig(Protocol):
    key: str
    links: dict[str, str | None]


class _RunnerConfig(Protocol):
    schema_version: str
    config_path: str
    config_sha256: str
    prompts: _PromptsConfig
    workflow: _WorkflowConfig
    model: _ModelConfig


class _RunnerConfigModule(Protocol):
    def load_runner_config(
        self, config_path: str, *, repo_root: Path
    ) -> _RunnerConfig: ...


class _RunnerModule(Protocol):
    def main(self, argv: list[str] | None = None) -> int: ...


def _import_runner_config_module() -> _RunnerConfigModule:
    _ = sys.modules.pop("scripts.generation.runner_config", None)
    try:
        return cast(
            _RunnerConfigModule,
            cast(object, importlib.import_module("scripts.generation.runner_config")),
        )
    except ModuleNotFoundError:
        pytest.fail(
            "缺少 scripts.generation.runner_config；YAML 配置加载契约尚未实现",
            pytrace=False,
        )


def _install_runner_config_stub() -> None:
    module = types.ModuleType("scripts.generation.runner_config")

    def load_runner_config(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        raise AssertionError("测试需显式 monkeypatch load_runner_config")

    setattr(module, "load_runner_config", load_runner_config)
    sys.modules["scripts.generation.runner_config"] = module


def _import_runner_module() -> _RunnerModule:
    _install_runner_config_stub()
    _ = sys.modules.pop("scripts.generation.comfyui_part1_generate", None)
    return cast(
        _RunnerModule,
        cast(
            object, importlib.import_module("scripts.generation.comfyui_part1_generate")
        ),
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_assets(repo_root: Path) -> tuple[Path, Path, Path]:
    x_path = repo_root / "data/prompts/x.json"
    y_path = repo_root / "data/prompts/y.yaml"
    workflow_path = repo_root / "data/workflows/example.json"
    x_path.parent.mkdir(parents=True, exist_ok=True)
    y_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    x_path.write_text(json.dumps({"schema": "", "items": []}) + "\n", encoding="utf-8")
    y_path.write_text("schema: prompt-y-table/v2\nitems: []\n", encoding="utf-8")
    workflow_path.write_text('{"3": {"class_type": "KSampler"}}\n', encoding="utf-8")
    return x_path, y_path, workflow_path


def test_load_runner_config_happy_path_resolves_repo_relative_paths_and_hashes(
    tmp_path: Path,
) -> None:
    module = _import_runner_config_module()
    x_path, y_path, workflow_path = _write_assets(tmp_path)
    config_path = tmp_path / "data/runs/example.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            [
                "schema_version: image-run-config/v1",
                "model:",
                "  key: nai-4-full",
                "  name: NAI 4 Full",
                "  family: novelai",
                "  links:",
                "    homepage: https://example.com/model",
                "    huggingface: null",
                "    civitai: null",
                "  description:",
                "    zh: 测试模型",
                "    en: Test model",
                "  tags:",
                "    - anime",
                "prompts:",
                "  x_path: data/prompts/x.json",
                "  y_path: data/prompts/y.yaml",
                "workflow:",
                "  path: data/workflows/example.json",
                "  ksampler_node_id: '3'",
                "generation:",
                "  template: '{gender}{y}{quality}'",
                "  base_seed: 123",
                "  negative_prompt: bad,",
                "  append_negative_prompt: nsfw, nipples,",
                "  width: 832",
                "  height: 1216",
                "  batch_size: 1",
                "  steps: 28",
                "  cfg: 5.5",
                "  denoise: 1.0",
                "  sampler_name: euler",
                "  scheduler: normal",
                "selection:",
                "  x_limit: 1",
                "  y_limit: 2",
                "  x_indexes: [0]",
                "  y_indexes: [1]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = module.load_runner_config(str(config_path), repo_root=tmp_path)

    assert config.schema_version == "image-run-config/v1"
    assert config.config_path == "data/runs/example.yaml"
    assert config.config_sha256 == _sha256_file(config_path)
    assert Path(config.prompts.x.path) == x_path
    assert Path(config.prompts.y.path) == y_path
    assert config.prompts.x.repo_relative_path == "data/prompts/x.json"
    assert config.prompts.y.repo_relative_path == "data/prompts/y.yaml"
    assert config.prompts.x.sha256 == _sha256_file(x_path)
    assert config.prompts.y.sha256 == _sha256_file(y_path)
    assert Path(config.workflow.path) == workflow_path
    assert config.workflow.repo_relative_path == "data/workflows/example.json"
    assert config.workflow.sha256 == _sha256_file(workflow_path)
    assert config.model.key == "nai-4-full"
    assert config.model.links == {
        "homepage": "https://example.com/model",
        "huggingface": None,
        "civitai": None,
    }


def test_load_runner_config_rejects_unknown_key(tmp_path: Path) -> None:
    module = _import_runner_config_module()
    _ = _write_assets(tmp_path)
    config_path = tmp_path / "data/runs/example.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "schema_version: image-run-config/v1\nunknown_key: true\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown_key"):
        module.load_runner_config(str(config_path), repo_root=tmp_path)


def test_load_runner_config_rejects_invalid_schema_version(tmp_path: Path) -> None:
    module = _import_runner_config_module()
    _ = _write_assets(tmp_path)
    config_path = tmp_path / "data/runs/example.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "schema_version: image-run-config/v999\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema_version"):
        module.load_runner_config(str(config_path), repo_root=tmp_path)


def test_load_runner_config_rejects_repo_external_path(tmp_path: Path) -> None:
    module = _import_runner_config_module()
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    config_path = tmp_path / "data/runs/example.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            [
                "schema_version: image-run-config/v1",
                "model:",
                "  key: demo",
                "  name: Demo",
                "  family: test",
                "  links:",
                "    homepage: null",
                "    huggingface: null",
                "    civitai: null",
                "  description:",
                "    zh: ''",
                "    en: ''",
                "  tags: []",
                "prompts:",
                f"  x_path: {outside}",
                "  y_path: data/prompts/y.yaml",
                "workflow:",
                "  path: data/workflows/example.json",
                "  ksampler_node_id: null",
                "generation:",
                "  template: '{gender}{y}'",
                "  base_seed: 1",
                "  negative_prompt: null",
                "  append_negative_prompt: null",
                "  width: null",
                "  height: null",
                "  batch_size: null",
                "  steps: null",
                "  cfg: null",
                "  denoise: null",
                "  sampler_name: null",
                "  scheduler: null",
                "selection:",
                "  x_limit: null",
                "  y_limit: null",
                "  x_indexes: null",
                "  y_indexes: null",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="repo-relative"):
        module.load_runner_config(str(config_path), repo_root=tmp_path)


def test_fresh_run_rejects_deprecated_business_env_before_loading_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _import_runner_module()
    config_path = tmp_path / "example.yaml"
    config_path.write_text("schema_version: image-run-config/v1\n", encoding="utf-8")
    monkeypatch.setenv("COMFYUI_NEGATIVE_PROMPT", "legacy-should-fail")

    exit_code = runner.main(
        ["--dry-run", "--config", str(config_path), "--run-dir", str(tmp_path / "run")]
    )

    assert exit_code == 2
    assert "COMFYUI_NEGATIVE_PROMPT" in capsys.readouterr().err


def test_load_runner_config_exposes_compact_model_snapshot_only(tmp_path: Path) -> None:
    module = _import_runner_config_module()
    _ = _write_assets(tmp_path)
    config_path = tmp_path / "data/runs/example.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            [
                "schema_version: image-run-config/v1",
                "model:",
                "  key: demo",
                "  name: Demo",
                "  family: test",
                "  links:",
                "    homepage: https://example.com",
                "    huggingface: null",
                "    civitai: null",
                "  description:",
                "    zh: 测试",
                "    en: Test",
                "  tags: [anime]",
                "prompts:",
                "  x_path: data/prompts/x.json",
                "  y_path: data/prompts/y.yaml",
                "workflow:",
                "  path: data/workflows/example.json",
                "  ksampler_node_id: null",
                "generation:",
                "  template: '{gender}{y}'",
                "  base_seed: 1",
                "  negative_prompt: null",
                "  append_negative_prompt: null",
                "  width: null",
                "  height: null",
                "  batch_size: null",
                "  steps: null",
                "  cfg: null",
                "  denoise: null",
                "  sampler_name: null",
                "  scheduler: null",
                "selection:",
                "  x_limit: null",
                "  y_limit: null",
                "  x_indexes: null",
                "  y_indexes: null",
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = module.load_runner_config(str(config_path), repo_root=tmp_path)

    assert config.model.key == "demo"
    assert not hasattr(config.model, "workflow")
    assert not hasattr(config.prompts, "items")
