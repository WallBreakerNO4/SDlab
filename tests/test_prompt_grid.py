# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generation.prompt_grid import (
    MAX_SEED,
    X_INFO_TYPE_KEY,
    build_prompt_cell,
    compute_prompt_hash,
    derive_seed,
    normalize_prompt,
    read_x_descriptions,
    read_x_rows,
    read_y_rows,
    render_positive_prompt,
)


X_JSON = ROOT / "data" / "prompts" / "X" / "common_prompts.json"
Y_JSON = ROOT / "data" / "prompts" / "Y" / "300_NAI_Styles_Table-test.json"


def test_read_x_rows_maps_real_columns_and_ignores_trailing_empty_column():
    rows = read_x_rows(X_JSON)

    assert rows
    first = rows[0]
    assert set(first.keys()) == {
        "gender",
        "characters",
        "series",
        "rating",
        "general",
        "quality",
        X_INFO_TYPE_KEY,
    }
    assert first["gender"] == "1girl,"
    assert first["characters"] == "amiya \\(arknights\\),"
    assert first["quality"] == "masterpiece,high score,great score,absurdres,year 2025,"
    assert first[X_INFO_TYPE_KEY] == "normal"


def test_read_y_rows_uses_artists_column_by_default():
    rows = read_y_rows(Y_JSON)

    assert rows
    assert rows[0]["y"].startswith("gochisousama")


def test_render_positive_prompt_template_and_segment_rules():
    x_row = {
        "gender": " 1girl ",
        "characters": "",
        "series": " arknights, ",
        "rating": "safe",
        "general": "solo, smiling",
        "quality": " masterpiece, ",
    }

    rendered = render_positive_prompt(x_row, " artist-name ")

    assert rendered == "1girl,arknights,safe,artist-name,solo, smiling,masterpiece,"


def test_normalize_prompt_whitespace_and_comma_rules_keep_case():
    raw = "\n  A ,B,\tC  ,  d  \n"

    normalized = normalize_prompt(raw)

    assert normalized == "A, B, C, d"


def test_compute_prompt_hash_uses_normalized_prompt_sha256_hex():
    prompt = "  A ,B,\nC  "
    expected = hashlib.sha256("A, B, C".encode("utf-8")).hexdigest()

    assert compute_prompt_hash(prompt) == expected


def test_derive_seed_is_deterministic_and_uses_sha256_first_16_hex_modulo():
    base_seed = 42
    x_index = 3
    y_index = 5
    expected = (
        int(
            hashlib.sha256(
                f"{base_seed}:{x_index}:{y_index}".encode("utf-8")
            ).hexdigest()[:16],
            16,
        )
        % MAX_SEED
    )

    actual = derive_seed(base_seed, x_index, y_index)

    assert actual == expected
    assert derive_seed(base_seed, x_index, y_index) == actual
    assert derive_seed(base_seed, x_index, y_index + 1) != actual
    assert 0 <= actual < MAX_SEED


def test_build_prompt_cell_contains_prompt_hash_and_seed():
    x_rows = read_x_rows(X_JSON)
    y_rows = read_y_rows(Y_JSON)

    cell = build_prompt_cell(x_rows[0], y_rows[0], base_seed=123, x_index=0, y_index=0)
    positive_prompt = cell["positive_prompt"]

    assert isinstance(positive_prompt, str)

    assert set(cell.keys()) == {"positive_prompt", "prompt_hash", "seed"}
    assert (
        cell["prompt_hash"]
        == hashlib.sha256(normalize_prompt(positive_prompt).encode("utf-8")).hexdigest()
    )
    assert cell["seed"] == derive_seed(123, 0, 0)


def test_read_x_descriptions_returns_list_with_zh_and_en_keys(tmp_path):
    json_path = tmp_path / "test.json"
    json_path.write_text(
        '{"items": [{"description": {"zh": "测试", "en": "test"}}]}',
        encoding="utf-8",
    )

    result = read_x_descriptions(json_path)

    assert result == [{"zh": "测试", "en": "test"}]


def test_read_x_descriptions_missing_description_returns_empty_strings(tmp_path):
    json_path = tmp_path / "test.json"
    json_path.write_text(
        '{"items": [{"tags": {"gender": [{"text": "1girl"}]}}]}',
        encoding="utf-8",
    )

    result = read_x_descriptions(json_path)

    assert result == [{"zh": "", "en": ""}]


def test_read_x_descriptions_preserves_markdown_newlines(tmp_path):
    json_path = tmp_path / "test.json"
    json_path.write_text(
        '{"items": [{"description": {"zh": "标题\\n- 列表项1\\n- 列表项2", "en": "Title\\n- Item 1\\n- Item 2"}}]}',
        encoding="utf-8",
    )

    result = read_x_descriptions(json_path)

    assert result == [
        {"zh": "标题\n- 列表项1\n- 列表项2", "en": "Title\n- Item 1\n- Item 2"}
    ]


def test_read_x_descriptions_non_dict_item_returns_empty_strings(tmp_path):
    json_path = tmp_path / "test.json"
    json_path.write_text(
        '{"items": ["string", 123, {"description": {"zh": "测试"}}]}',
        encoding="utf-8",
    )

    result = read_x_descriptions(json_path)

    assert result == [
        {"zh": "", "en": ""},
        {"zh": "", "en": ""},
        {"zh": "测试", "en": ""},
    ]


def test_read_x_descriptions_invalid_json_top_level_returns_empty_list(tmp_path):
    json_path = tmp_path / "test.json"
    json_path.write_text('["not", "a", "dict"]', encoding="utf-8")

    result = read_x_descriptions(json_path)

    assert result == []


def test_read_x_descriptions_missing_items_returns_empty_list(tmp_path):
    json_path = tmp_path / "test.json"
    json_path.write_text('{"other": "data"}', encoding="utf-8")

    result = read_x_descriptions(json_path)

    assert result == []


def test_read_x_descriptions_items_not_list_returns_empty_list(tmp_path):
    json_path = tmp_path / "test.json"
    json_path.write_text('{"items": "not a list"}', encoding="utf-8")

    result = read_x_descriptions(json_path)

    assert result == []


def test_read_x_descriptions_strips_whitespace(tmp_path):
    json_path = tmp_path / "test.json"
    json_path.write_text(
        '{"items": [{"description": {"zh": "  测试  ", "en": "  test  "}}]}',
        encoding="utf-8",
    )

    result = read_x_descriptions(json_path)

    assert result == [{"zh": "测试", "en": "test"}]
