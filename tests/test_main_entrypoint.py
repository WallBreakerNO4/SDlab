import json
import sys
from pathlib import Path

import pytest

from main import main


def test_main_dry_run_creates_run_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "test-run"
    args = [
        "--dry-run",
        "--run-dir",
        str(run_dir),
        "--x-csv",
        "data/prompts/X/common_prompts.csv",
        "--y-csv",
        "data/prompts/Y/300_NAI_Styles_Table-test.csv",
        "--x-limit",
        "2",
        "--y-limit",
        "1",
    ]

    exit_code = main(args)

    assert exit_code == 0
    assert run_dir.exists()

    run_json_path = run_dir / "run.json"
    assert run_json_path.exists()

    run_data = json.loads(run_json_path.read_text(encoding="utf-8"))

    assert run_data["dry_run"] is True
    assert run_data["selection"]["x_count"] == 2
    assert run_data["selection"]["y_count"] == 1
    assert run_data["selection"]["total_cells"] == 2

    metadata_path = run_dir / "metadata.jsonl"
    assert metadata_path.exists()

    metadata_lines = metadata_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(metadata_lines) == 2

    for line in metadata_lines:
        record = json.loads(line)
        assert record["status"] == "skipped"
        assert record["skip_reason"] == "dry_run"


def test_main_propagates_help_to_script_runner() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0


def test_main_propagates_invalid_args_exit_code() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--invalid-arg"])

    assert exc_info.value.code == 2
