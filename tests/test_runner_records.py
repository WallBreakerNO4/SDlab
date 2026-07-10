# pyright: reportMissingImports=false, reportPrivateUsage=false

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generation.prompt_grid import X_INFO_TYPE_KEY
from scripts.generation.runner_records import _build_base_metadata_record


def _build_record(x_row: dict[str, object]) -> dict[str, object]:
    return _build_base_metadata_record(
        status="success",
        x_index=1,
        y_index=2,
        x_row=x_row,
        y_value="artist-a",
        positive_prompt="rendered prompt",
        prompt_hash="prompt-hash",
        seed=42,
        generation_params={"seed": 42},
        workflow_hash="workflow-hash",
        attempt=1,
    )


def test_build_base_metadata_record_preserves_newbie_nested_x_fields() -> None:
    characters = [
        {
            "n": "amiya (arknights)",
            "gender": "1girl",
            "appearance": "brown hair, blue eyes",
        },
        {
            "n": "doctor (arknights)",
            "gender": "1other",
            "clothing": "hooded coat",
        },
    ]
    general = {
        "count": "2people",
        "artists": "artist-a",
        "quality": "masterpiece, best quality",
    }
    caption = "Amiya and the Doctor stand together.\nThe full scene remains intact."
    x_row: dict[str, object] = {
        "characters": characters,
        "general": general,
        "caption": caption,
        X_INFO_TYPE_KEY: "normal",
    }

    record = _build_record(x_row)

    assert record["x_fields"] == {
        "characters": characters,
        "general": general,
        "caption": caption,
    }
    assert record["x_info_type"] == "normal"
    assert X_INFO_TYPE_KEY not in record["x_fields"]
    assert "characters" not in record
    assert "caption" not in record

    serialized = json.dumps(record, ensure_ascii=False)
    round_tripped = json.loads(serialized)

    assert round_tripped["x_fields"]["characters"] == characters
    assert round_tripped["x_fields"]["general"] == general
    assert round_tripped["x_fields"]["caption"] == caption


def test_build_base_metadata_record_keeps_common_five_x_fields() -> None:
    common_fields = {
        "gender": "1girl,",
        "characters": "amiya,",
        "series": "arknights,",
        "rating": "safe,",
        "general": "solo,",
    }
    x_row: dict[str, object] = {
        **common_fields,
        X_INFO_TYPE_KEY: "normal",
    }

    record = _build_record(x_row)

    assert record["x_fields"] == common_fields
    assert record["x_info_type"] == "normal"
    assert X_INFO_TYPE_KEY not in record["x_fields"]
