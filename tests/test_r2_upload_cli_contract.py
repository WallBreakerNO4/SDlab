# pyright: basic, reportMissingImports=false

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.upload_images_to_r2 import main


def test_dry_run_prints_structured_summary_placeholder(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["--dry-run", "--run-dir", "run-20260217T072414Z"])

    assert exit_code == 0

    output = capsys.readouterr().out
    assert "planned_variants" in output
    assert "planned_uploads" in output
