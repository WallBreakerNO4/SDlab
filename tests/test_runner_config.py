# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false, reportUnusedCallResult=false, reportUnknownVariableType=false

import hashlib
import importlib
import json
import sys
import types
from pathlib import Path
from typing import Protocol, cast

import pytest
from PIL import Image

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
    download: _PromptRef | None
    ksampler_node_id: str | None


class _GenerationConfig(Protocol):
    template: str
    quality_prompt: str
    base_seed: int
    negative_prompt: str | None
    append_negative_prompt: str | None
    width: int | None
    height: int | None
    batch_size: int | None
    steps: int | None
    cfg: float | None
    denoise: float | None
    sampler_name: str | None
    scheduler: str | None


class _SelectionConfig(Protocol):
    x_limit: int | None
    y_limit: int | None
    x_indexes: list[int] | None
    y_indexes: list[int] | None


class _AssetsConfig(Protocol):
    cover_image: _PromptRef | None
    homepage_images: list[_PromptRef]


class _ModelConfig(Protocol):
    key: str
    name: str
    family: str
    artist_weight_profile: str
    links: dict[str, str | None]
    description: dict[str, str]


class _RunnerConfig(Protocol):
    schema_version: str
    backend: str
    config_path: str
    config_sha256: str
    prompts: _PromptsConfig
    workflow: _WorkflowConfig
    model: _ModelConfig
    generation: _GenerationConfig
    selection: _SelectionConfig
    assets: _AssetsConfig


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


def test_load_real_newbie_config_preserves_local_asset_contract() -> None:
    module = _import_runner_config_module()
    config_path = ROOT / "data/models/newbie-image-exp0.1/config.yaml"

    config = module.load_runner_config(
        config_path.relative_to(ROOT).as_posix(),
        repo_root=ROOT,
    )

    assert config.backend == "comfyui"
    assert config.model.family == "newbie"
    assert config.prompts.x.repo_relative_path == "data/prompts/X/newbie_prompts.yaml"
    assert (
        config.prompts.y.repo_relative_path
        == "data/prompts/Y/300_NAI_Styles_Table-test.yaml"
    )
    assert (
        config.workflow.repo_relative_path
        == "data/models/newbie-image-exp0.1/api.json"
    )
    assert config.workflow.download is None
    assert config.workflow.ksampler_node_id is None

    assert config.config_sha256 == _sha256_file(config_path)
    assert config.prompts.x.sha256 == _sha256_file(Path(config.prompts.x.path))
    assert config.prompts.y.sha256 == _sha256_file(Path(config.prompts.y.path))
    assert config.workflow.sha256 == _sha256_file(Path(config.workflow.path))


def _write_image(path: Path, *, image_format: str = "PNG") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), (120, 80, 40)).save(path, format=image_format)


def _write_png(path: Path) -> None:
    _write_image(path, image_format="PNG")


def _write_assets(repo_root: Path) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    x_path = repo_root / "data/prompts/x.json"
    y_path = repo_root / "data/prompts/y.yaml"
    workflow_path = repo_root / "data/models/example/api.json"
    workflow_download_path = repo_root / "data/models/example/workflow.json"
    cover_image_path = repo_root / "data/models/example/image.jpg"
    homepage_first = repo_root / "data/models/example/images/001.png"
    homepage_second = repo_root / "data/models/example/images/002.png"
    x_path.parent.mkdir(parents=True, exist_ok=True)
    y_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    x_path.write_text(json.dumps({"schema": "", "items": []}) + "\n", encoding="utf-8")
    y_path.write_text("schema: prompt-y-table/v3\nitems: []\n", encoding="utf-8")
    workflow_path.write_text('{"3": {"class_type": "KSampler"}}\n', encoding="utf-8")
    workflow_download_path.write_text('{"version": 1}\n', encoding="utf-8")
    _write_png(cover_image_path)
    _write_png(homepage_first)
    _write_png(homepage_second)
    return (
        x_path,
        y_path,
        workflow_path,
        workflow_download_path,
        cover_image_path,
        homepage_first,
        homepage_second,
    )


def _write_assets_with_cover_extension(
    repo_root: Path, *, cover_suffix: str
) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    if cover_suffix not in {".png", ".jpg", ".jpeg", ".webp", ".avif"}:
        raise ValueError(f"不支持的测试封面图扩展名: {cover_suffix}")

    x_path = repo_root / "data/prompts/x.json"
    y_path = repo_root / "data/prompts/y.yaml"
    workflow_path = repo_root / "data/models/example/api.json"
    workflow_download_path = repo_root / "data/models/example/workflow.json"
    cover_image_path = repo_root / f"data/models/example/image{cover_suffix}"
    homepage_first = repo_root / "data/models/example/images/001.png"
    homepage_second = repo_root / "data/models/example/images/002.png"
    x_path.parent.mkdir(parents=True, exist_ok=True)
    y_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    x_path.write_text(json.dumps({"schema": "", "items": []}) + "\n", encoding="utf-8")
    y_path.write_text("schema: prompt-y-table/v3\nitems: []\n", encoding="utf-8")
    workflow_path.write_text('{"3": {"class_type": "KSampler"}}\n', encoding="utf-8")
    workflow_download_path.write_text('{"version": 1}\n', encoding="utf-8")
    _write_png(cover_image_path)
    _write_png(homepage_first)
    _write_png(homepage_second)
    return (
        x_path,
        y_path,
        workflow_path,
        workflow_download_path,
        cover_image_path,
        homepage_first,
        homepage_second,
    )


def _valid_config_text(*, schema_version: str = "image-run-config/v1") -> str:
    return "\n".join(
        [
            f"schema_version: {schema_version}",
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
            "prompts:",
            "  x_path: data/prompts/x.json",
            "  y_path: data/prompts/y.yaml",
            "workflow:",
            "  ksampler_node_id: '3'",
            "generation:",
            "  template: '{quality}{gender}{y}'",
            "  quality_prompt: 'masterpiece, best quality,'",
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
    )


def test_load_runner_config_happy_path_resolves_repo_relative_paths_and_hashes(
    tmp_path: Path,
) -> None:
    module = _import_runner_config_module()
    (
        x_path,
        y_path,
        workflow_path,
        workflow_download_path,
        cover_image_path,
        homepage_first,
        homepage_second,
    ) = _write_assets(tmp_path)
    config_path = tmp_path / "data/models/example/config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_valid_config_text(), encoding="utf-8")

    config = module.load_runner_config(str(config_path), repo_root=tmp_path)

    assert config.schema_version == "image-run-config/v1"
    assert config.config_path == "data/models/example/config.yaml"
    assert config.config_sha256 == _sha256_file(config_path)
    assert Path(config.prompts.x.path) == x_path
    assert Path(config.prompts.y.path) == y_path
    assert config.prompts.x.repo_relative_path == "data/prompts/x.json"
    assert config.prompts.y.repo_relative_path == "data/prompts/y.yaml"
    assert config.prompts.x.sha256 == _sha256_file(x_path)
    assert config.prompts.y.sha256 == _sha256_file(y_path)
    assert Path(config.workflow.path) == workflow_path
    assert config.workflow.repo_relative_path == "data/models/example/api.json"
    assert config.workflow.sha256 == _sha256_file(workflow_path)
    assert config.workflow.download is not None
    assert Path(config.workflow.download.path) == workflow_download_path
    assert (
        config.workflow.download.repo_relative_path
        == "data/models/example/workflow.json"
    )
    assert config.workflow.download.sha256 == _sha256_file(workflow_download_path)
    assert config.workflow.ksampler_node_id == "3"
    assert config.assets.cover_image is not None
    assert Path(config.assets.cover_image.path) == cover_image_path
    assert config.assets.cover_image.repo_relative_path == "data/models/example/image.jpg"
    assert config.assets.cover_image.sha256 == _sha256_file(cover_image_path)
    assert [asset.repo_relative_path for asset in config.assets.homepage_images] == [
        "data/models/example/images/001.png",
        "data/models/example/images/002.png",
    ]
    assert [Path(asset.path) for asset in config.assets.homepage_images] == [
        homepage_first,
        homepage_second,
    ]
    assert config.model.key == "nai-4-full"
    assert config.model.name == "NAI 4 Full"
    assert config.model.family == "novelai"
    assert config.model.artist_weight_profile == "identity"
    assert config.model.links == {
        "homepage": "https://example.com/model",
        "huggingface": None,
        "civitai": None,
    }
    assert config.model.description == {"zh": "测试模型", "en": "Test model"}
    assert config.generation.template == "{quality}{gender}{y}"
    assert config.generation.quality_prompt == "masterpiece, best quality,"
    assert config.generation.base_seed == 123
    assert config.generation.negative_prompt == "bad,"
    assert config.generation.append_negative_prompt == "nsfw, nipples,"
    assert config.generation.width == 832
    assert config.generation.height == 1216
    assert config.generation.batch_size == 1
    assert config.generation.steps == 28
    assert config.generation.cfg == 5.5
    assert config.generation.denoise == 1.0
    assert config.generation.sampler_name == "euler"
    assert config.generation.scheduler == "normal"
    assert config.selection.x_limit == 1
    assert config.selection.y_limit == 2
    assert config.selection.x_indexes == [0]
    assert config.selection.y_indexes == [1]


def test_load_runner_config_accepts_png_cover_image_when_jpg_is_missing(
    tmp_path: Path,
) -> None:
    module = _import_runner_config_module()
    (
        x_path,
        y_path,
        workflow_path,
        workflow_download_path,
        cover_image_path,
        homepage_first,
        homepage_second,
    ) = _write_assets_with_cover_extension(tmp_path, cover_suffix=".png")
    config_path = tmp_path / "data/models/example/config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_valid_config_text(), encoding="utf-8")

    config = module.load_runner_config(str(config_path), repo_root=tmp_path)

    assert Path(config.prompts.x.path) == x_path
    assert Path(config.prompts.y.path) == y_path
    assert Path(config.workflow.path) == workflow_path
    assert config.workflow.download is not None
    assert Path(config.workflow.download.path) == workflow_download_path
    assert config.assets.cover_image is not None
    assert Path(config.assets.cover_image.path) == cover_image_path
    assert config.assets.cover_image.repo_relative_path == "data/models/example/image.png"
    assert config.assets.cover_image.sha256 == _sha256_file(cover_image_path)
    assert [asset.repo_relative_path for asset in config.assets.homepage_images] == [
        "data/models/example/images/001.png",
        "data/models/example/images/002.png",
    ]
    assert [Path(asset.path) for asset in config.assets.homepage_images] == [
        homepage_first,
        homepage_second,
    ]


def test_load_runner_config_rejects_multiple_cover_image_files(
    tmp_path: Path,
) -> None:
    module = _import_runner_config_module()
    _ = _write_assets(tmp_path)
    png_cover_path = tmp_path / "data/models/example/image.png"
    _write_png(png_cover_path)
    config_path = tmp_path / "data/models/example/config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_valid_config_text(), encoding="utf-8")

    with pytest.raises(ValueError, match=r"多个 image\.\* 文件"):
        module.load_runner_config(str(config_path), repo_root=tmp_path)


@pytest.mark.parametrize(
    ("cover_suffix", "expected_repo_relative_path"),
    [
        (".jpeg", "data/models/example/image.jpeg"),
        (".webp", "data/models/example/image.webp"),
        (".avif", "data/models/example/image.avif"),
    ],
)
def test_load_runner_config_accepts_supported_cover_image_extensions(
    tmp_path: Path,
    cover_suffix: str,
    expected_repo_relative_path: str,
) -> None:
    module = _import_runner_config_module()
    (_, _, _, _, cover_image_path, _, _) = _write_assets_with_cover_extension(
        tmp_path,
        cover_suffix=cover_suffix,
    )
    config_path = tmp_path / "data/models/example/config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_valid_config_text(), encoding="utf-8")

    config = module.load_runner_config(str(config_path), repo_root=tmp_path)

    assert config.assets.cover_image is not None
    assert Path(config.assets.cover_image.path) == cover_image_path
    assert config.assets.cover_image.repo_relative_path == expected_repo_relative_path
    assert config.assets.cover_image.sha256 == _sha256_file(cover_image_path)


def test_load_runner_config_accepts_uppercase_cover_image_extension(
    tmp_path: Path,
) -> None:
    module = _import_runner_config_module()
    (_, _, _, _, _, _, _) = _write_assets_with_cover_extension(
        tmp_path,
        cover_suffix=".png",
    )
    lowercase_cover = tmp_path / "data/models/example/image.png"
    uppercase_cover = tmp_path / "data/models/example/image.PNG"
    lowercase_cover.rename(uppercase_cover)
    config_path = tmp_path / "data/models/example/config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_valid_config_text(), encoding="utf-8")

    config = module.load_runner_config(str(config_path), repo_root=tmp_path)

    assert config.assets.cover_image is not None
    assert Path(config.assets.cover_image.path) == uppercase_cover
    assert config.assets.cover_image.repo_relative_path == "data/models/example/image.PNG"


def test_load_runner_config_rejects_unknown_key(tmp_path: Path) -> None:
    module = _import_runner_config_module()
    _ = _write_assets(tmp_path)
    config_path = tmp_path / "data/models/example/config.yaml"
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
    config_path = tmp_path / "data/models/example/config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _valid_config_text(schema_version="image-run-config/v999"), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="schema_version"):
        module.load_runner_config(str(config_path), repo_root=tmp_path)


def test_load_runner_config_rejects_repo_external_path(tmp_path: Path) -> None:
    module = _import_runner_config_module()
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    config_path = tmp_path / "data/models/example/config.yaml"
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
                "prompts:",
                f"  x_path: {outside}",
                "  y_path: data/prompts/y.yaml",
                "workflow:",
                "  ksampler_node_id: null",
                "generation:",
                "  template: '{gender}{y}'",
                "  quality_prompt: 'masterpiece,'",
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


def test_load_runner_config_rejects_absolute_asset_path_inside_repo(
    tmp_path: Path,
) -> None:
    module = _import_runner_config_module()
    x_path, *_ = _write_assets(tmp_path)
    config_path = tmp_path / "data/models/example/config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _valid_config_text().replace("data/prompts/x.json", str(x_path)),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="repo-relative"):
        module.load_runner_config(str(config_path), repo_root=tmp_path)


def test_load_runner_config_rejects_empty_model_key(tmp_path: Path) -> None:
    module = _import_runner_config_module()
    _ = _write_assets(tmp_path)
    config_path = tmp_path / "data/models/example/config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _valid_config_text().replace("  key: nai-4-full", "  key: ''"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="model.key"):
        module.load_runner_config(str(config_path), repo_root=tmp_path)


def test_load_runner_config_rejects_non_slug_model_key(tmp_path: Path) -> None:
    module = _import_runner_config_module()
    _ = _write_assets(tmp_path)
    config_path = tmp_path / "data/models/example/config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _valid_config_text().replace("  key: nai-4-full", "  key: NAI_4_FULL"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="model.key"):
        module.load_runner_config(str(config_path), repo_root=tmp_path)


def test_load_runner_config_defaults_anima_artist_weight_profile_to_square(
    tmp_path: Path,
) -> None:
    module = _import_runner_config_module()
    _ = _write_assets(tmp_path)
    config_path = tmp_path / "data/models/example/config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _valid_config_text()
        .replace("  family: novelai", "  family: anima")
        .replace("  key: nai-4-full", "  key: anima-base-1"),
        encoding="utf-8",
    )

    config = module.load_runner_config(str(config_path), repo_root=tmp_path)

    assert config.model.artist_weight_profile == "square"


def test_load_runner_config_accepts_explicit_artist_weight_profile(
    tmp_path: Path,
) -> None:
    module = _import_runner_config_module()
    _ = _write_assets(tmp_path)
    config_path = tmp_path / "data/models/example/config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _valid_config_text()
        .replace("  family: novelai", "  family: anima")
        .replace("  key: nai-4-full", "  key: anima-base-1")
        .replace(
            "  family: anima",
            "  family: anima\n  artist_weight_profile: identity",
        ),
        encoding="utf-8",
    )

    config = module.load_runner_config(str(config_path), repo_root=tmp_path)

    assert config.model.artist_weight_profile == "identity"


def test_load_runner_config_rejects_invalid_artist_weight_profile(
    tmp_path: Path,
) -> None:
    module = _import_runner_config_module()
    _ = _write_assets(tmp_path)
    config_path = tmp_path / "data/models/example/config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _valid_config_text().replace(
            "  family: novelai",
            "  family: novelai\n  artist_weight_profile: double",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="artist_weight_profile"):
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
    config_path = tmp_path / "data/models/example/config.yaml"
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
                "prompts:",
                "  x_path: data/prompts/x.json",
                "  y_path: data/prompts/y.yaml",
                "workflow:",
                "  ksampler_node_id: null",
                "generation:",
                "  template: '{gender}{y}'",
                "  quality_prompt: 'masterpiece,'",
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


def test_load_runner_config_accepts_run_directory_and_reads_config_yaml(
    tmp_path: Path,
) -> None:
    module = _import_runner_config_module()
    _ = _write_assets(tmp_path)
    config_dir = tmp_path / "data/models/example"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(_valid_config_text(), encoding="utf-8")

    config = module.load_runner_config("data/models/example", repo_root=tmp_path)

    assert config.config_path == "data/models/example/config.yaml"
