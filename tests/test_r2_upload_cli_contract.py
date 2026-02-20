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
    run_dir = tmp_path / "run-20260217T072414Z"
    images_dir = run_dir / "images"
    images_dir.mkdir(parents=True)

    source = images_dir / "x0-y0.png"
    Image.new("RGB", (8, 6), (128, 64, 32)).save(source, format="PNG")

    (run_dir / "run.json").write_text(
        '{"run_id":"test","run_dir":"run-20260217T072414Z"}',
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
