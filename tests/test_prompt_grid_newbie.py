# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generation.prompt_grid import (
    NEWBIE_CHAR_SUBTAGS,
    NEWBIE_GENERAL_SUBTAGS,
    NEWBIE_X_SCHEMA,
    X_INFO_TYPE_KEY,
    _render_subtag,
    compute_prompt_hash,
    read_x_rows_newbie,
    render_positive_prompt_xml,
)


def _write_newbie_yaml(path: Path, body: str) -> None:
    path.write_text(
        f"schema: {NEWBIE_X_SCHEMA}\n{body}".strip() + "\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# _render_subtag
# --------------------------------------------------------------------------- #


def test_render_subtag_strips_bare_string() -> None:
    assert _render_subtag("  roxy migurdia  ") == "roxy migurdia"


def test_render_subtag_renders_weighted_tags_and_strips_trailing_comma() -> None:
    tags = [
        {"text": "red hair", "weight": 1.0},
        {"text": "blue eyes", "weight": 1.3},
    ]
    assert _render_subtag(tags) == "red hair, (blue eyes:1.3)"


def test_render_subtag_rejects_unsupported_type() -> None:
    with pytest.raises(ValueError, match="str 或 list"):
        _render_subtag(123)


# --------------------------------------------------------------------------- #
# read_x_rows_newbie
# --------------------------------------------------------------------------- #


_MINI_NEWBIE_YAML = """
items:
  - characters:
      - n: roxy migurdia
        gender: 1girl
        appearance:
          - text: red hair
            weight: 1.0
          - text: short hair
            weight: 1.3
        clothing: robe
      - n: second char
        gender: 1boy
    general:
      count: 1girl
      artists:
        - text: wlop
          weight: 1.1
      style: anime
      quality: masterpiece
    info:
      type: normal
"""


def test_read_x_rows_newbie_maps_structure(tmp_path: Path) -> None:
    ypath = tmp_path / "newbie.yaml"
    _write_newbie_yaml(ypath, _MINI_NEWBIE_YAML)

    rows = read_x_rows_newbie(ypath)

    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == {"characters", "general", X_INFO_TYPE_KEY, "caption"}

    characters = row["characters"]
    assert isinstance(characters, list)
    assert len(characters) == 2

    first = characters[0]
    assert set(first.keys()) <= set(NEWBIE_CHAR_SUBTAGS)
    assert first["n"] == "roxy migurdia"
    assert first["gender"] == "1girl"
    # list 形式走 weighted_tags 渲染并去尾逗号
    assert first["appearance"] == "red hair, (short hair:1.3)"
    assert first["clothing"] == "robe"

    second = characters[1]
    assert second["n"] == "second char"
    assert second["gender"] == "1boy"

    general = row["general"]
    assert isinstance(general, dict)
    assert set(general.keys()) <= set(NEWBIE_GENERAL_SUBTAGS)
    assert general["count"] == "1girl"
    assert general["artists"] == "(wlop:1.1)"
    assert general["style"] == "anime"
    assert general["quality"] == "masterpiece"

    assert row[X_INFO_TYPE_KEY] == "normal"


def test_read_x_rows_newbie_accepts_bare_string_and_weighted_list(tmp_path: Path) -> None:
    ypath = tmp_path / "mixed.yaml"
    _write_newbie_yaml(
        ypath,
        """
items:
  - characters:
      - n: bare string char
        appearance:
          - text: tag one
            weight: 1.0
          - text: tag two
            weight: 0.5
    general:
      other: bare string
      objects:
        - text: sword
          weight: 1.0
    info:
      type: normal
""",
    )

    rows = read_x_rows_newbie(ypath)
    char = rows[0]["characters"][0]
    assert char["n"] == "bare string char"
    assert char["appearance"] == "tag one, (tag two:0.5)"
    general = rows[0]["general"]
    assert general["other"] == "bare string"
    assert general["objects"] == "sword"


def test_read_x_rows_newbie_unknown_character_subtag_raises(tmp_path: Path) -> None:
    ypath = tmp_path / "bad-char.yaml"
    _write_newbie_yaml(
        ypath,
        """
items:
  - characters:
      - n: roxy
        typo_field: oops
    general:
      count: 1girl
    info:
      type: normal
""",
    )

    with pytest.raises(ValueError, match="未知子标签"):
        read_x_rows_newbie(ypath)


def test_read_x_rows_newbie_unknown_general_subtag_raises(tmp_path: Path) -> None:
    ypath = tmp_path / "bad-general.yaml"
    _write_newbie_yaml(
        ypath,
        """
items:
  - characters:
      - n: roxy
    general:
      count: 1girl
      bogus: x
    info:
      type: normal
""",
    )

    with pytest.raises(ValueError, match="未知子标签"):
        read_x_rows_newbie(ypath)


def test_read_x_rows_newbie_rejects_wrong_schema(tmp_path: Path) -> None:
    ypath = tmp_path / "common.yaml"
    # 故意写成 common 风格的空 schema
    ypath.write_text(
        'schema: ""\nitems: []\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema"):
        read_x_rows_newbie(ypath)


def test_read_x_rows_newbie_missing_info_defaults_to_empty(tmp_path: Path) -> None:
    ypath = tmp_path / "no-info.yaml"
    _write_newbie_yaml(
        ypath,
        """
items:
  - characters:
      - n: roxy
    general:
      count: 1girl
""",
    )

    rows = read_x_rows_newbie(ypath)
    assert rows[0][X_INFO_TYPE_KEY] == ""


# --------------------------------------------------------------------------- #
# render_positive_prompt_xml
# --------------------------------------------------------------------------- #


def _row(characters: list, general: dict) -> dict:
    return {"characters": characters, "general": general, X_INFO_TYPE_KEY: "normal"}


def test_render_xml_single_character_emits_only_non_empty_subtags() -> None:
    row = _row(
        characters=[
            {
                "n": "roxy migurdia",
                "gender": "1girl",
                "appearance": "",
                "clothing": "robe",
                "body_type": "",
                "expression": "smile",
                "action": "",
                "interaction": "",
                "position": "",
            }
        ],
        general={
            "count": "1girl",
            "artists": "",
            "style": "anime",
            "background": "",
            "environment": "",
            "perspective": "",
            "atmosphere": "",
            "lighting": "",
            "quality": "",
            "objects": "",
            "other": "",
        },
    )

    rendered = render_positive_prompt_xml(row, y_value="")

    assert rendered == (
        "<character_1>\n"
        "<n>roxy migurdia</n>\n"
        "<gender>1girl</gender>\n"
        "<clothing>robe</clothing>\n"
        "<expression>smile</expression>\n"
        "</character_1>\n\n"
        "<general_tags>\n"
        "<count>1girl</count>\n"
        "<style>anime</style>\n"
        "</general_tags>"
    )


def test_render_xml_multi_characters_numbering_is_contiguous() -> None:
    row = _row(
        characters=[
            {"n": "roxy migurdia", "gender": "1girl"},
            {"n": "second char", "gender": "1boy"},
        ],
        general={"count": "2girls"},
    )

    rendered = render_positive_prompt_xml(row, y_value="")

    assert "<character_1>" in rendered
    assert "<character_2>" in rendered
    assert "</character_1>\n\n<character_2>" in rendered


def test_render_xml_y_value_overrides_artists() -> None:
    row = _row(
        characters=[{"n": "roxy"}],
        general={"count": "1girl", "artists": "internal-artist"},
    )

    rendered = render_positive_prompt_xml(row, y_value="  gochisousama, ")

    assert "<artists>gochisousama</artists>" in rendered
    assert "internal-artist" not in rendered


def test_render_xml_y_value_strips_trailing_comma() -> None:
    row = _row(
        characters=[{"n": "roxy"}],
        general={"count": "1girl"},
    )

    rendered = render_positive_prompt_xml(row, y_value="wlop, piyodera mucha,")

    assert "<artists>wlop, piyodera mucha</artists>" in rendered


def test_render_xml_falls_back_to_general_artists_when_y_empty() -> None:
    row = _row(
        characters=[{"n": "roxy"}],
        general={"count": "1girl", "artists": "fallback-artist"},
    )

    rendered = render_positive_prompt_xml(row, y_value="   ")

    assert "<artists>fallback-artist</artists>" in rendered


def test_render_xml_omits_artists_when_both_empty() -> None:
    row = _row(
        characters=[{"n": "roxy"}],
        general={"count": "1girl", "artists": ""},
    )

    rendered = render_positive_prompt_xml(row, y_value="")

    assert "<artists>" not in rendered


def test_render_xml_merges_quality_prompt_into_quality_tag() -> None:
    row = _row(
        characters=[{"n": "roxy"}],
        general={"count": "1girl", "quality": "masterpiece"},
    )

    rendered = render_positive_prompt_xml(row, y_value="", quality_prompt="best quality")

    assert "<quality>best quality, masterpiece</quality>" in rendered


def test_render_xml_quality_uses_only_non_empty_parts() -> None:
    row = _row(
        characters=[{"n": "roxy"}],
        general={"count": "1girl", "quality": "masterpiece"},
    )

    # quality_prompt 为空 -> 只剩 general.quality
    rendered = render_positive_prompt_xml(row, y_value="", quality_prompt="   ")

    assert "<quality>masterpiece</quality>" in rendered


def test_render_xml_quality_omitted_when_both_empty() -> None:
    row = _row(
        characters=[{"n": "roxy"}],
        general={"count": "1girl", "quality": ""},
    )

    rendered = render_positive_prompt_xml(row, y_value="", quality_prompt=None)

    assert "<quality>" not in rendered


def test_render_xml_blocks_separated_by_double_newline() -> None:
    row = _row(
        characters=[{"n": "roxy"}, {"n": "amiya"}],
        general={"count": "2girls"},
    )

    rendered = render_positive_prompt_xml(row, y_value="")

    # 角色块之间、最后一个角色块与 general_tags 之间都用 \n\n 分隔
    assert "</character_1>\n\n<character_2>" in rendered
    assert "</character_2>\n\n<general_tags>" in rendered


def test_render_xml_has_no_outer_root_node() -> None:
    row = _row(
        characters=[{"n": "roxy"}],
        general={"count": "1girl"},
    )

    rendered = render_positive_prompt_xml(row, y_value="")

    assert not rendered.startswith("<root")
    assert not rendered.startswith("<?xml")
    # 第一行应当是 <character_1>
    assert rendered.startswith("<character_1>")


def test_render_xml_preserves_subtag_order() -> None:
    row = _row(
        characters=[
            {
                "n": "roxy",
                "gender": "1girl",
                "appearance": "red hair",
                "clothing": "robe",
                "body_type": "slender",
                "expression": "smile",
                "action": "standing",
                "interaction": "looking at viewer",
                "position": "outdoors",
            }
        ],
        general={
            "count": "1girl",
            "artists": "wlop",
            "style": "anime",
            "background": "simple",
            "environment": "outdoors",
            "perspective": "from above",
            "atmosphere": "calm",
            "lighting": "soft",
            "quality": "masterpiece",
            "objects": "sword",
            "other": "other tag",
        },
    )

    rendered = render_positive_prompt_xml(row, y_value="")

    char_block = rendered.split("<general_tags>")[0]
    char_subtag_order = [
        line.split(">")[0].lstrip("<")
        for line in char_block.splitlines()
        if line.startswith("<") and not line.startswith("</") and not line.startswith("<character")
    ]
    assert char_subtag_order == list(NEWBIE_CHAR_SUBTAGS)

    general_block = rendered.split("<general_tags>")[1]
    general_subtag_order = [
        line.split(">")[0].lstrip("<")
        for line in general_block.splitlines()
        if line.startswith("<") and not line.startswith("</")
    ]
    assert general_subtag_order == list(NEWBIE_GENERAL_SUBTAGS)


# --------------------------------------------------------------------------- #
# compute_prompt_hash 对 XML 串的确定性
# --------------------------------------------------------------------------- #


def test_compute_prompt_hash_deterministic_for_xml_string() -> None:
    row = _row(
        characters=[{"n": "roxy", "gender": "1girl"}],
        general={"count": "1girl", "quality": "masterpiece"},
    )

    xml_a = render_positive_prompt_xml(row, y_value="wlop", quality_prompt="best quality")
    xml_b = render_positive_prompt_xml(row, y_value="wlop", quality_prompt="best quality")

    assert xml_a == xml_b
    assert compute_prompt_hash(xml_a) == compute_prompt_hash(xml_b)


def test_compute_prompt_hash_differs_for_different_xml() -> None:
    row = _row(
        characters=[{"n": "roxy", "gender": "1girl"}],
        general={"count": "1girl"},
    )

    xml_a = render_positive_prompt_xml(row, y_value="wlop")
    xml_b = render_positive_prompt_xml(row, y_value="rurudo")

    assert xml_a != xml_b
    assert compute_prompt_hash(xml_a) != compute_prompt_hash(xml_b)


# --------------------------------------------------------------------------- #
# read_x_rows_newbie caption 字段
# --------------------------------------------------------------------------- #


_NEWBIE_YAML_WITH_CAPTION = """
items:
  - characters:
      - n: amiya
        gender: 1girl
    general:
      count: 1girl
    info:
      type: normal
    caption:
      zh: "明日方舟的阿米娅，面部特写。"
      en: "A close-up portrait of Amiya from Arknights."
"""


def test_read_x_rows_newbie_reads_caption_en(tmp_path: Path) -> None:
    ypath = tmp_path / "caption.yaml"
    _write_newbie_yaml(ypath, _NEWBIE_YAML_WITH_CAPTION)

    rows = read_x_rows_newbie(ypath)

    assert rows[0]["caption"] == "A close-up portrait of Amiya from Arknights."


_NEWBIE_YAML_CAPTION_ZH_ONLY = """
items:
  - characters:
      - n: amiya
    general:
      count: 1girl
    info:
      type: normal
    caption:
      zh: "明日方舟的阿米娅。"
"""


def test_read_x_rows_newbie_caption_falls_back_to_zh(tmp_path: Path) -> None:
    ypath = tmp_path / "caption-zh.yaml"
    _write_newbie_yaml(ypath, _NEWBIE_YAML_CAPTION_ZH_ONLY)

    rows = read_x_rows_newbie(ypath)

    assert rows[0]["caption"] == "明日方舟的阿米娅。"


def test_read_x_rows_newbie_caption_optional_defaults_empty(tmp_path: Path) -> None:
    ypath = tmp_path / "no-caption.yaml"
    _write_newbie_yaml(ypath, _MINI_NEWBIE_YAML)

    rows = read_x_rows_newbie(ypath)

    assert rows[0]["caption"] == ""


_NEWBIE_YAML_CAPTION_BARE_STRING = """
items:
  - characters:
      - n: amiya
    general:
      count: 1girl
    info:
      type: normal
    caption: a bare string caption
"""


def test_read_x_rows_newbie_caption_accepts_bare_string(tmp_path: Path) -> None:
    ypath = tmp_path / "caption-bare.yaml"
    _write_newbie_yaml(ypath, _NEWBIE_YAML_CAPTION_BARE_STRING)

    rows = read_x_rows_newbie(ypath)

    assert rows[0]["caption"] == "a bare string caption"


_NEWBIE_YAML_CAPTION_BAD_TYPE = """
items:
  - characters:
      - n: amiya
    general:
      count: 1girl
    info:
      type: normal
    caption:
      - 1
      - 2
      - 3
"""


def test_read_x_rows_newbie_caption_rejects_invalid_type(tmp_path: Path) -> None:
    ypath = tmp_path / "caption-bad.yaml"
    _write_newbie_yaml(ypath, _NEWBIE_YAML_CAPTION_BAD_TYPE)

    with pytest.raises(ValueError, match="caption"):
        read_x_rows_newbie(ypath)


def test_render_positive_prompt_xml_ignores_caption() -> None:
    """caption 不参与 XML 渲染，不影响 prompt_hash 基础。"""
    row_with_caption = {
        "characters": [{"n": "roxy", "gender": "1girl"}],
        "general": {"count": "1girl"},
        X_INFO_TYPE_KEY: "normal",
        "caption": "a natural language caption",
    }
    row_without_caption = {
        "characters": [{"n": "roxy", "gender": "1girl"}],
        "general": {"count": "1girl"},
        X_INFO_TYPE_KEY: "normal",
        "caption": "",
    }

    xml_a = render_positive_prompt_xml(row_with_caption, y_value="wlop")
    xml_b = render_positive_prompt_xml(row_without_caption, y_value="wlop")

    assert xml_a == xml_b
    assert "caption" not in xml_a.lower()