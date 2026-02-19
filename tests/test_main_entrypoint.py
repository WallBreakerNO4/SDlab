import json
from pathlib import Path
from typing import cast

import pytest

from main import main


def test_main_dry_run_creates_run_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "test-run"
    args = [
        "--dry-run",
        "--run-dir",
        str(run_dir),
        "--x-json",
        "data/prompts/X/common_prompts.json",
        "--y-json",
        "data/prompts/Y/300_NAI_Styles_Table-test.json",
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

    run_data = cast(
        dict[str, object], json.loads(run_json_path.read_text(encoding="utf-8"))
    )

    assert run_data["dry_run"] is True
    selection = cast(dict[str, object], run_data["selection"])
    assert selection["x_count"] == 2
    assert selection["y_count"] == 1
    assert selection["total_cells"] == 2

    metadata_path = run_dir / "metadata.jsonl"
    assert metadata_path.exists()

    metadata_lines = metadata_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(metadata_lines) == 2

    for line in metadata_lines:
        record = cast(dict[str, object], json.loads(line))
        assert record["status"] == "skipped"
        assert record["skip_reason"] == "dry_run"


def test_main_propagates_help_to_script_runner() -> None:
    with pytest.raises(SystemExit) as exc_info:
        _ = main(["--help"])

    assert exc_info.value.code == 0


def test_main_propagates_invalid_args_exit_code() -> None:
    with pytest.raises(SystemExit) as exc_info:
        _ = main(["--invalid-arg"])

    assert exc_info.value.code == 2
