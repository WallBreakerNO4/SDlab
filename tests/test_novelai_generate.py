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
