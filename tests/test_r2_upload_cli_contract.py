# pyright: basic, reportMissingImports=false

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.upload_images_to_r2 import main


def test_dry_run_prints_structured_summary_placeholder(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = tmp_path / "contract-run"
    images_dir = run_dir / "images"
    images_dir.mkdir(parents=True)

    source = images_dir / "x0-y0.png"
    Image.new("RGB", (8, 6), (128, 64, 32)).save(source, format="PNG")

    (run_dir / "run.json").write_text(
        (
            "{"
            '"run_id":"contract-run",'
            '"run_key":"contract-run",'
            '"run_dir":"contract-run",'
            '"config_schema_version":"image-run-config/v1",'
            '"config_path":"data/runs/example.yaml",'
            '"config_sha256":"' + ("deadbeef" * 8) + '",'
            '"model":{'
            '"key":"chenkinnoob-xl-rf",'
            '"name":"ChenkinNoob XL Rectified Flow",'
            '"family":"stable-diffusion-xl",'
            '"links":{"homepage":null,"huggingface":null,"civitai":null},'
            '"description":{"zh":"示例配置","en":"Example config"},'
            '"tags":["example","sdxl"]'
            "},"
            '"config_snapshot":{'
            '"prompts":{'
            '"x_path":"data/prompts/X/common_prompts.yaml",'
            '"y_path":"data/prompts/Y/300_NAI_Styles_Table-test.yaml",'
            '"x_sha256":"' + ("a" * 64) + '",'
            '"y_sha256":"' + ("b" * 64) + '"},'
            '"workflow":{'
            '"path":"data/comfyui-flow/CKNOOBRF.json",'
            '"sha256":"' + ("c" * 64) + '",'
            '"ksampler_node_id":"6"},'
            '"generation":{'
            '"template":"{gender}{characters}{series}{rating}{y}{general}{quality}",'
            '"base_seed":123,'
            '"negative_prompt":null,'
            '"append_negative_prompt":"nsfw, nipples, pussy, nude,",'
            '"width":1024,'
            '"height":1536,'
            '"batch_size":1,'
            '"steps":28,'
            '"cfg":3.5,'
            '"denoise":1.0,'
            '"sampler_name":"euler",'
            '"scheduler":"simple"'
            "},"
            '"selection":{"x_limit":null,"y_limit":null,"x_indexes":null,"y_indexes":null}'
            "}"
            "}"
        ),
        encoding="utf-8",
    )
    (run_dir / "metadata.jsonl").write_text(
        '{"status":"success","x_index":0,"y_index":0,"local_image_path":"images/x0-y0.png"}\n',
        encoding="utf-8",
    )

    exit_code = main(["--dry-run", "--run-dir", str(run_dir)])

    assert exit_code == 0

    output = capsys.readouterr().out
    assert "planned_variants" in output
    assert "planned_uploads" in output
