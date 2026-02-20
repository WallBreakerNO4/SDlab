# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

X_JSON = ROOT / "data" / "prompts" / "X" / "common_prompts.json"


def test_common_prompts_json_has_items_array():
    with open(X_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict)
    assert "items" in data
    items = data["items"]
    assert isinstance(items, list)
    assert len(items) > 0


def test_common_prompts_json_each_item_has_description_dict():
    with open(X_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data["items"]
    for item in items:
        assert "description" in item, f"Item missing 'description' field"
        description = item["description"]
        assert isinstance(description, dict), f"description must be a dict"


def test_common_prompts_json_each_item_has_zh_and_en_non_empty():
    with open(X_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data["items"]
    for i, item in enumerate(items):
        description = item["description"]
        assert "zh" in description, f"Item {i} missing 'description.zh'"
        assert "en" in description, f"Item {i} missing 'description.en'"
        zh = description["zh"]
        en = description["en"]
        assert isinstance(zh, str), f"Item {i}: description.zh must be string"
        assert isinstance(en, str), f"Item {i}: description.en must be string"
        assert len(zh.strip()) > 0, f"Item {i}: description.zh is empty"
        assert len(en.strip()) > 0, f"Item {i}: description.en is empty"


def test_common_prompts_json_info_index_preserved():
    with open(X_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data["items"]
    indices = [item["info"]["index"] for item in items]
    assert indices == list(range(len(indices)))
