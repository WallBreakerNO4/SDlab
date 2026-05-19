# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

X_YAML = ROOT / "data" / "prompts" / "X" / "common_prompts.yaml"
Y_YAMLS = [
    ROOT / "data" / "prompts" / "Y" / "300_NAI_Styles_Table.yaml",
    ROOT / "data" / "prompts" / "Y" / "300_NAI_Styles_Table-test.yaml",
]


def test_common_prompts_json_has_items_array():
    data = yaml.safe_load(X_YAML.read_text(encoding="utf-8"))

    assert isinstance(data, dict)
    assert "items" in data
    items = data["items"]
    assert isinstance(items, list)
    assert len(items) > 0


def test_common_prompts_json_each_item_has_description_dict():
    data = yaml.safe_load(X_YAML.read_text(encoding="utf-8"))

    items = data["items"]
    for item in items:
        assert "description" in item, f"Item missing 'description' field"
        description = item["description"]
        assert isinstance(description, dict), f"description must be a dict"


def test_common_prompts_json_each_item_has_zh_and_en_non_empty():
    data = yaml.safe_load(X_YAML.read_text(encoding="utf-8"))

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
    data = yaml.safe_load(X_YAML.read_text(encoding="utf-8"))

    items = data["items"]
    indices = [item["info"]["index"] for item in items]
    assert indices == list(range(len(indices)))


def test_y_prompt_assets_use_v3_tag_types():
    for path in Y_YAMLS:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))

        assert data["schema"] == "prompt-y-table/v3"
        items = data["items"]
        assert isinstance(items, list)
        assert len(items) > 0
        for item_index, item in enumerate(items):
            info = item["info"]
            assert "type" not in info, f"{path}: item {item_index} still has info.type"
            assert isinstance(info["index"], int)
            for tag_index, tag in enumerate(item["tags"]):
                assert tag.get("type") in {"general", "artists"}, (
                    f"{path}: item {item_index} tag {tag_index} has invalid type"
                )
