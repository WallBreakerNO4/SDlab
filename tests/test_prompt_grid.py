# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import hashlib
import sys
from pathlib import Path

import pytest

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
    read_y_rows_for_novelai,
    render_positive_prompt,
)


X_JSON = ROOT / "data" / "prompts" / "X" / "common_prompts.yaml"
Y_JSON = ROOT / "data" / "prompts" / "Y" / "300_NAI_Styles_Table-test.yaml"


def _write_y_yaml(path: Path, tags_yaml: str) -> None:
    path.write_text(
        f"""
schema: prompt-y-table/v3
items:
  - tags:
{tags_yaml}
    info:
      index: 0
""".lstrip(),
        encoding="utf-8",
    )


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
        X_INFO_TYPE_KEY,
    }
    assert first["gender"] == "1girl,"
    assert first["characters"] == "amiya \\(arknights\\),"
    assert first[X_INFO_TYPE_KEY] == "normal"


def test_read_y_rows_uses_artists_column_by_default():
    rows = read_y_rows(Y_JSON)

    assert rows
    assert rows[0]["y"].startswith("gochisousama")


def test_read_x_rows_rejects_legacy_quality_field(tmp_path: Path) -> None:
    legacy_yaml = tmp_path / "legacy.yaml"
    legacy_yaml.write_text(
        """
schema: ""
items:
  - tags:
      gender:
        - text: 1girl
          weight: 1.0
      quality:
        - text: masterpiece
          weight: 1.0
    info:
      index: 0
      type: normal
""".strip()
        + "\n",
        encoding="utf-8",
    )

    try:
        read_x_rows(legacy_yaml)
    except ValueError as exc:
        assert "tags.quality" in str(exc)
    else:
        raise AssertionError("旧 tags.quality 字段应被显式拒绝")


def test_render_positive_prompt_template_and_segment_rules():
    x_row = {
        "gender": " 1girl ",
        "characters": "",
        "series": " arknights, ",
        "rating": "safe",
        "general": "solo, smiling",
    }

    rendered = render_positive_prompt(x_row, " artist-name ", " masterpiece, ")

    assert rendered == "masterpiece,1girl,arknights,safe,artist-name,solo, smiling,"


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

    cell = build_prompt_cell(
        x_rows[0],
        y_rows[0],
        base_seed=123,
        x_index=0,
        y_index=0,
        quality_prompt="masterpiece,",
    )
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


def test_read_y_rows_artist_prefix_applies_only_to_artist_tags(tmp_path: Path):
    y_path = tmp_path / "y.yaml"
    _write_y_yaml(
        y_path,
        """
      - text: wlop
        weight: 1.1
        type: artists
      - text: furry
        weight: 1.0
        type: general
""",
    )

    rows = read_y_rows(y_path, artist_prefix="@")

    assert rows == [{"y": "(@wlop:1.1),furry,"}]


def test_read_y_rows_square_profile_applies_only_to_artist_weights(tmp_path: Path):
    y_path = tmp_path / "y.yaml"
    _write_y_yaml(
        y_path,
        """
      - text: wlop
        weight: 1.1
        type: artists
      - text: piyodera mucha
        weight: 0.81
        type: artists
      - text: furry
        weight: 1.1
        type: general
""",
    )

    rows = read_y_rows(y_path, artist_prefix="@", artist_weight_profile="square")

    assert rows == [{"y": "(@wlop:1.21),(@piyodera mucha:0.656),(furry:1.1),"}]


def test_read_y_rows_rejects_unknown_artist_weight_profile(tmp_path: Path):
    y_path = tmp_path / "y.yaml"
    _write_y_yaml(
        y_path,
        """
      - text: wlop
        weight: 1.1
        type: artists
""",
    )

    with pytest.raises(ValueError, match="artist_weight_profile"):
        read_y_rows(y_path, artist_weight_profile="double")


def test_read_y_rows_without_artist_prefix_keeps_artist_text(tmp_path: Path):
    y_path = tmp_path / "y.yaml"
    _write_y_yaml(
        y_path,
        """
      - text: wlop
        weight: 1.1
        type: artists
      - text: furry
        weight: 1.0
        type: general
""",
    )

    rows = read_y_rows(y_path)

    assert rows == [{"y": "(wlop:1.1),furry,"}]


def test_read_y_rows_rejects_legacy_info_type(tmp_path: Path):
    y_path = tmp_path / "legacy-y.yaml"
    y_path.write_text(
        """
schema: prompt-y-table/v2
items:
  - tags:
      - text: wlop
        weight: 1.0
    info:
      index: 0
      type: artists
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema"):
        read_y_rows(y_path)


def test_read_y_rows_rejects_missing_tag_type(tmp_path: Path):
    y_path = tmp_path / "missing-type.yaml"
    _write_y_yaml(
        y_path,
        """
      - text: wlop
        weight: 1.0
""",
    )

    with pytest.raises(ValueError, match="type"):
        read_y_rows(y_path)


def test_read_y_rows_for_novelai_adds_artist_prefix():
    rows = read_y_rows_for_novelai(Y_JSON)

    assert rows
    first = rows[0]["y"]
    # weight=1.0 -> plain artist:tag
    assert "artist:gochisousama \\(tanin050\\)" in first
    # weight=0.59 -> 0.59::artist:tag ::
    assert "0.59::artist:tsukareta san ::" in first
    # weight=0.349 -> 0.349::artist:tag ::
    assert "0.349::artist:cutesexyrobutts ::" in first


def test_read_y_rows_for_novelai_weight_one_no_prefix():
    from scripts.generation.prompt_grid import _render_novelai_weighted_tags

    tags = [{"text": "rurudo", "weight": 1.0, "type": "artists"}]
    assert _render_novelai_weighted_tags(tags) == "artist:rurudo,"


def test_read_y_rows_for_novelai_with_weight():
    from scripts.generation.prompt_grid import _render_novelai_weighted_tags

    tags = [{"text": "rurudo", "weight": 1.21, "type": "artists"}]
    assert _render_novelai_weighted_tags(tags) == "1.21::artist:rurudo ::,"


def test_read_y_rows_for_novelai_multiple_tags():
    from scripts.generation.prompt_grid import _render_novelai_weighted_tags

    tags = [
        {"text": "rurudo", "weight": 1.21, "type": "artists"},
        {"text": "furry", "weight": 1.0, "type": "general"},
    ]
    result = _render_novelai_weighted_tags(tags)
    assert result == "1.21::artist:rurudo ::,furry,"


def test_read_y_rows_for_novelai_empty():
    from scripts.generation.prompt_grid import _render_novelai_weighted_tags

    assert _render_novelai_weighted_tags([]) == ""
    with pytest.raises(ValueError, match="tags"):
        _render_novelai_weighted_tags("not a list")
    with pytest.raises(ValueError, match="text"):
        _render_novelai_weighted_tags([{"no_text": "x"}])
