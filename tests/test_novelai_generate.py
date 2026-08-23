# pyright: basic, reportPrivateUsage=false

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generation import novelai_client, novelai_generate
from scripts.generation.prompt_grid import X_INFO_TYPE_KEY


def _args(
    *,
    negative_prompt: str | None = None,
    append_negative_prompt: str | None = "nsfw,nipples,",
    cfg: float = 5.0,
) -> argparse.Namespace:
    return argparse.Namespace(
        negative_prompt=negative_prompt,
        append_negative_prompt=append_negative_prompt,
        width=832,
        height=1216,
        batch_size=1,
        steps=28,
        cfg=cfg,
        denoise=None,
        sampler_name="k_euler_ancestral",
        scheduler=None,
    )


def test_novelai_final_negative_appends_only_for_normal_rows() -> None:
    args = _args(negative_prompt="lowres,")

    normal = novelai_generate._novelai_final_negative(
        args,
        None,
        {X_INFO_TYPE_KEY: "normal"},
    )
    nsfw = novelai_generate._novelai_final_negative(
        args,
        None,
        {X_INFO_TYPE_KEY: "nsfw"},
    )

    assert normal == "lowres, nsfw,nipples,"
    assert nsfw == "lowres,"


def test_novelai_generation_fingerprint_changes_with_effective_params() -> None:
    first = novelai_generate._novelai_generation_fingerprint(
        _args(cfg=5.0),
        model="nai-diffusion-4-5-full",
    )
    second = novelai_generate._novelai_generation_fingerprint(
        _args(cfg=6.0),
        model="nai-diffusion-4-5-full",
    )

    assert first != second
    assert len(first) == 64
    assert len(second) == 64


def test_apply_novelai_fingerprint_updates_run_payload_snapshot() -> None:
    payload: dict[str, object] = {
        "workflow_api_sha256": "not_loaded",
        "config_snapshot": {"workflow": {"api_sha256": ""}},
    }

    novelai_generate._apply_novelai_fingerprint_to_run_payload(
        payload,
        fingerprint="a" * 64,
    )

    assert payload["workflow_api_sha256"] == "a" * 64
    assert payload["config_snapshot"] == {"workflow": {"api_sha256": "a" * 64}}


def test_normalize_model_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="未知 NovelAI 模型"):
        novelai_client._normalize_model("some-new-model")


@pytest.mark.parametrize(
    "model_key",
    ["nai-diffusion-5-full", "nai-diffusion-5-curated"],
)
def test_v5_config_dry_run_prints_totals_and_example_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    model_key: str,
) -> None:
    # load_runner_config 以 cwd 为 repo root，先固定回仓库根目录。
    monkeypatch.chdir(ROOT)

    exit_code = novelai_generate.main(
        [
            "--config",
            f"data/models/{model_key}/config.yaml",
            "--dry-run",
            "--run-dir",
            str(tmp_path / "run"),
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "组合总数:" in out
    assert "示例正向提示词:" in out


def test_novelai_client_passes_request_timeout_to_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeNovelAI:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(novelai_client, "NovelAI", FakeNovelAI)

    _ = novelai_client.NovelAIAPIClient(
        api_key="test-key",
        request_timeout_s=12.5,
    )

    assert captured["api_key"] == "test-key"
    assert captured["timeout"] == 12.5


# --- _convert_prompt_to_novelai_format tests ---


def test_convert_positive_weight() -> None:
    assert (
        novelai_client._convert_prompt_to_novelai_format("(rurudo:1.21)")
        == "1.21::rurudo ::"
    )


def test_convert_weight_below_one() -> None:
    assert (
        novelai_client._convert_prompt_to_novelai_format("(dark:0.9)")
        == "0.9::dark ::"
    )


def test_convert_weight_one_returns_plain_tag() -> None:
    assert novelai_client._convert_prompt_to_novelai_format("(tag:1.0)") == "tag"
    assert novelai_client._convert_prompt_to_novelai_format("(tag:1.000)") == "tag"


def test_convert_negative_weight() -> None:
    assert (
        novelai_client._convert_prompt_to_novelai_format("(hat:-1)")
        == "-1::hat ::"
    )


def test_convert_tag_with_colon() -> None:
    assert (
        novelai_client._convert_prompt_to_novelai_format("(artist:name:1.1)")
        == "1.1::artist:name ::"
    )


def test_convert_strips_trailing_zeros() -> None:
    assert (
        novelai_client._convert_prompt_to_novelai_format("(tag:1.10)")
        == "1.1::tag ::"
    )
    assert (
        novelai_client._convert_prompt_to_novelai_format("(tag:2.00)")
        == "2::tag ::"
    )


def test_convert_invalid_weight_preserved() -> None:
    assert (
        novelai_client._convert_prompt_to_novelai_format("(tag:not_a_number)")
        == "(tag:not_a_number)"
    )


def test_convert_empty_string() -> None:
    assert novelai_client._convert_prompt_to_novelai_format("") == ""


def test_convert_none_returns_empty() -> None:
    assert novelai_client._convert_prompt_to_novelai_format(None) == ""


def test_convert_no_weighted_tags_unchanged() -> None:
    assert (
        novelai_client._convert_prompt_to_novelai_format("masterpiece, best quality")
        == "masterpiece, best quality"
    )


def test_convert_mixed_tags() -> None:
    result = novelai_client._convert_prompt_to_novelai_format(
        "masterpiece,(rurudo:1.21),best quality,(dark:0.9),"
    )
    assert result == "masterpiece,1.21::rurudo ::,best quality,0.9::dark ::,"


def test_convert_worker_uses_converted_prompt_for_api() -> None:
    """Verify novelai_worker passes converted prompt to client.generate
    but metadata keeps original format. Y-axis is already NovelAI format."""
    calls: list[dict[str, object]] = []

    class FakeClient:
        def generate(self, **kwargs: Any) -> list[object]:
            calls.append(kwargs)
            return []

    client = FakeClient()
    worker = novelai_client.novelai_worker(client=client, model="nai-diffusion-4-5-full")

    # Y-axis is already NovelAI format from read_y_rows_for_novelai
    plan = argparse.Namespace(
        positive_prompt="masterpiece,1.21::artist:rurudo ::,",
        negative_prompt="(lowres:0.8),",
        x_index=0,
        y_index=0,
        x_row={},
        y_value="1.21::artist:rurudo ::,",
        prompt_hash="abc",
        seed=42,
        generation_params={},
        workflow_hash="wf",
        save_image_prefix="test",
        x_description={"zh": "", "en": ""},
        attempt=1,
    )

    args = argparse.Namespace(
        width=832,
        height=1216,
        steps=28,
        cfg=5.0,
        sampler_name="k_euler_ancestral",
        batch_size=1,
    )

    def fake_final_negative(*a: Any, **kw: Any) -> str:
        return "(lowres:0.8),"

    def fake_build_meta(**kwargs: Any) -> dict[str, object]:
        return kwargs

    worker(
        args,
        Path("/tmp"),
        None,
        plan,
        None,
        None,
        fake_final_negative,
        None,
        None,
        fake_build_meta,
        lambda: "2024-01-01T00:00:00",
    )

    assert len(calls) == 1
    # Y-axis already in NovelAI format, should pass through unchanged
    assert calls[0]["prompt"] == "masterpiece,1.21::artist:rurudo ::,"
    # Negative prompt still in WebUI format, should be converted
    assert calls[0]["negative_prompt"] == "0.8::lowres ::,"
