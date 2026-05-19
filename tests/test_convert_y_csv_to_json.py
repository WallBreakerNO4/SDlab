import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.other.convert_y_csv_to_json import convert_csv_to_yaml, parse_weighted_tags


def test_parse_weighted_tags_can_attach_default_tag_type() -> None:
    assert parse_weighted_tags("wlop,(furry)", default_tag_type="general") == [
        {"text": "wlop", "weight": 1.0, "type": "general"},
        {"text": "furry", "weight": 1.1, "type": "general"},
    ]


def test_convert_y_csv_to_yaml_writes_v3_tag_types(tmp_path: Path) -> None:
    csv_path = tmp_path / "y.csv"
    out_path = tmp_path / "y.yaml"
    csv_path.write_text(
        "Index,Artists\n"
        '433,"wlop,furry,"\n',
        encoding="utf-8",
    )

    count = convert_csv_to_yaml(
        csv_path,
        out_path,
        schema="prompt-y-table/v3",
        tags_column="Artists",
        index_column="Index",
        default_tag_type="general",
    )

    payload = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert count == 1
    assert payload == {
        "schema": "prompt-y-table/v3",
        "items": [
            {
                "tags": [
                    {"text": "wlop", "weight": 1.0, "type": "general"},
                    {"text": "furry", "weight": 1.0, "type": "general"},
                ],
                "info": {"index": 433},
            }
        ],
    }
