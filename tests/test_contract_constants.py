# pyright: basic, reportPrivateUsage=false

"""跨语言契约常量一致性守卫（Python 侧）。

run key / style_key / y_index 的镜像实现分散在 Python、TypeScript、SQL 三侧；
本文件与 tests/contract-constants.test.ts 共享
tests/fixtures/contract-constants.json 的行为样本，任一处漂移都会在
pytest 或 pnpm test 中失败。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generation import runner_selection
from scripts.generation.prompt_grid import (
    Y_STYLE_KEY,
    _normalize_collection_id as prompt_grid_normalize,
    _y_identity_fields,
    read_y_rows,
)
from scripts.other.backfill_run_style_items import (
    _normalize_collection_id as backfill_normalize,
    parse_style_keys_by_y_index,
)
from scripts.run_naming import RUN_KEY_RE, validate_run_key

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "contract-constants.json"


def _load_fixture() -> dict[str, object]:
    return cast(
        dict[str, object], json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    )


def _read_repo_file(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _migration_sources() -> list[str]:
    migrations_dir = ROOT / "supabase" / "migrations"
    return [
        path.read_text(encoding="utf-8")
        for path in sorted(migrations_dir.glob("*.sql"))
    ]


def _canonicalize_pattern(pattern: str) -> str:
    """只归一三端语义等价的方言写法，其余差异必须显式暴露。"""
    return pattern.replace("(?:", "(").replace(r"\d", "[0-9]")


def _extract_ts_pattern(relative_path: str, constant: str) -> str:
    source = _read_repo_file(relative_path)
    match = re.search(rf"{constant}\s*=\s*/([^/]+)/", source)
    assert match, f"{constant} 必须保留正则字面量声明"
    return match.group(1)


def _extract_sql_patterns(field_name: str) -> list[str]:
    pattern = re.compile(rf"{field_name}\s*!~\s*'([^']+)'")
    return [
        match.group(1)
        for source in _migration_sources()
        for match in pattern.finditer(source)
    ]


def test_run_key_mirrors_share_one_pattern() -> None:
    ts_pattern = _extract_ts_pattern("lib/comfyui-types.ts", "RUN_DIR_REGEX")
    sql_patterns = _extract_sql_patterns("run_dir")
    assert sql_patterns, "SQL 中必须存在 run_dir 形态校验"

    expected = _canonicalize_pattern(ts_pattern)
    assert _canonicalize_pattern(RUN_KEY_RE.pattern) == expected
    for pattern in sql_patterns:
        assert _canonicalize_pattern(pattern) == expected, pattern


def test_run_key_corpus_matches_python_validation() -> None:
    cases = cast(dict[str, list[str]], _load_fixture()["runKey"])
    for value in cases["valid"]:
        assert RUN_KEY_RE.fullmatch(value), value
        assert validate_run_key(value, field_name="run_key") == value
    for value in cases["invalid"]:
        assert RUN_KEY_RE.fullmatch(value) is None, value
        with pytest.raises(ValueError):
            validate_run_key(value, field_name="run_key")

    # validate_run_key 在匹配前 strip 输入，负责把 CLI/配置输入归一成规范形态；
    # 正则本身只接受规范形态（Web/SQL 侧不承担 strip）。
    assert RUN_KEY_RE.fullmatch(" abc ") is None
    assert validate_run_key(" abc ", field_name="run_key") == "abc"


def test_style_key_shape_mirrors_share_one_pattern() -> None:
    ts_pattern = _extract_ts_pattern("lib/style-favorites.ts", "STYLE_KEY_REGEX")
    sql_patterns = _extract_sql_patterns("style_key")
    assert sql_patterns, "SQL 中必须存在 style_key 形态校验"

    expected = _canonicalize_pattern(ts_pattern)
    for pattern in sql_patterns:
        assert _canonicalize_pattern(pattern) == expected, pattern


def test_style_key_producers_match_the_canonical_shape() -> None:
    canonical = _canonicalize_pattern(
        _extract_ts_pattern("lib/style-favorites.ts", "STYLE_KEY_REGEX")
    )
    reference = re.compile(canonical)

    fields = _y_identity_fields(
        collection_id="300-nai-styles-table",
        item={"info": {"index": 9}},
    )
    assert fields[Y_STYLE_KEY] == "300-nai-styles-table:9"
    assert reference.fullmatch(fields[Y_STYLE_KEY])

    payload = {
        "collection_id": "300-nai-styles-table",
        "items": [
            {"info": {"index": 5}, "tags": []},
            {"info": {"index": 3}, "tags": []},
            {"info": {"index": 9}, "tags": []},
        ],
    }
    style_keys = parse_style_keys_by_y_index(
        json.dumps(payload).encode("utf-8"), source_name="whatever.yaml"
    )
    assert style_keys == {
        0: "300-nai-styles-table:5",
        1: "300-nai-styles-table:3",
        2: "300-nai-styles-table:9",
    }
    for style_key in style_keys.values():
        assert reference.fullmatch(style_key), style_key


def test_collection_id_normalization_copies_agree() -> None:
    cases = cast(
        list[dict[str, str]], _load_fixture()["collectionIdNormalization"]
    )
    for case in cases:
        value = case["input"]
        assert prompt_grid_normalize(value) == case["normalized"], value
        assert backfill_normalize(value) == case["normalized"], value


def test_y_index_producers_stay_zero_based_positions(tmp_path: Path) -> None:
    payload = {
        "schema": "prompt-y-table/v3",
        "collection_id": "coll",
        "items": [
            {
                "info": {"index": 5},
                "tags": [{"text": "a", "weight": 1.0, "type": "artists"}],
            },
            {
                "info": {"index": 3},
                "tags": [{"text": "b", "weight": 1.0, "type": "general"}],
            },
            {
                "info": {"index": 9},
                "tags": [{"text": "c", "weight": 1.0, "type": "artists"}],
            },
        ],
    }
    y_path = tmp_path / "y.yaml"
    y_path.write_text(json.dumps(payload), encoding="utf-8")

    rows = read_y_rows(y_path)
    selected = runner_selection._select_rows(rows, None, None, "y")
    assert [item.index for item in selected] == [0, 1, 2]
    assert [item.value[Y_STYLE_KEY] for item in selected] == [
        "coll:5",
        "coll:3",
        "coll:9",
    ]

    # 子集选择（--y-indexes / limit）必须保留原始 0-based 位置，而不是重新编号。
    subset = runner_selection._select_rows(rows, None, "1,2", "y")
    assert [item.index for item in subset] == [1, 2]
    assert [item.value[Y_STYLE_KEY] for item in subset] == ["coll:3", "coll:9"]

    limited = runner_selection._select_rows(rows, 2, None, "y")
    assert [item.index for item in limited] == [0, 1]

    replayed = runner_selection._select_rows_by_fixed_indexes(
        rows=rows, indexes=[2], axis_name="y"
    )
    assert [item.index for item in replayed] == [2]

    with pytest.raises(ValueError):
        runner_selection._select_rows_by_fixed_indexes(
            rows=rows, indexes=[-1], axis_name="y"
        )
