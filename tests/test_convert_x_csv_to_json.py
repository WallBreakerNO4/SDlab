# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.other.convert_x_csv_to_json import convert_csv_to_json


def test_convert_x_csv_to_json_maps_type_and_descriptions(tmp_path: Path) -> None:
    csv_path = tmp_path / "x.csv"
    out_path = tmp_path / "x.json"

    csv_path.write_text(
        "\n".join(
            [
                "Gender tags,Character(s) tags,Series tags,Rating tags,General tags,Qulity tags,Type,description_zh,description_en",
                '"1girl,","amiya,","arknights,","safe,","solo,","masterpiece,",normal,"中文描述","English description"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    count = convert_csv_to_json(csv_path, out_path, schema="", item_type="sfw")

    assert count == 1
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    item = payload["items"][0]
    assert item["info"]["type"] == "normal"
    assert item["description"] == {"zh": "中文描述", "en": "English description"}


def test_convert_x_csv_to_json_fallbacks_when_columns_empty_or_missing(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "x.csv"
    out_path = tmp_path / "x.json"

    csv_path.write_text(
        "\n".join(
            [
                "Gender tags,Character(s) tags,Series tags,Rating tags,General tags,Qulity tags,Type",
                '"1girl,","amiya,","arknights,","safe,","solo,","masterpiece,",',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    count = convert_csv_to_json(csv_path, out_path, schema="", item_type="sfw")

    assert count == 1
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    item = payload["items"][0]
    assert item["info"]["type"] == "sfw"
    assert item["description"] == {"zh": "", "en": ""}
