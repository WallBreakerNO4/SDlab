from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.other.convert_y_csv_to_json import parse_weighted_tags  # noqa: E402


X_COLUMN_MAPPING: dict[str, str] = {
    "Gender tags": "gender",
    "Character(s) tags": "characters",
    "Series tags": "series",
    "Rating tags": "rating",
    "General tags": "general",
    "Qulity tags": "quality",
}

TYPE_COLUMN = "Type"
DESCRIPTION_ZH_COLUMN = "description_zh"
DESCRIPTION_EN_COLUMN = "description_en"


def convert_csv_to_json(
    csv_path: Path,
    out_path: Path,
    *,
    schema: str,
    item_type: str,
) -> int:
    items: list[dict[str, object]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for i, row in enumerate(reader):
            tags: dict[str, list[dict[str, object]]] = {}
            for source_col, key in X_COLUMN_MAPPING.items():
                raw_value = row.get(source_col, "")
                value = "" if raw_value is None else raw_value
                tags[key] = parse_weighted_tags(value)

            raw_type = row.get(TYPE_COLUMN, "")
            type_value = "" if raw_type is None else raw_type.strip()
            info_type = type_value if type_value else item_type

            raw_desc_zh = row.get(DESCRIPTION_ZH_COLUMN, "")
            desc_zh = "" if raw_desc_zh is None else raw_desc_zh.strip()

            raw_desc_en = row.get(DESCRIPTION_EN_COLUMN, "")
            desc_en = "" if raw_desc_en is None else raw_desc_en.strip()

            items.append(
                {
                    "tags": tags,
                    "info": {"index": i, "type": info_type},
                    "description": {"zh": desc_zh, "en": desc_en},
                }
            )

    payload = {"schema": schema, "items": items}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(items)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert prompt X CSV file to JSON asset."
    )
    parser.add_argument("csv_path", type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: next to CSV with .json)",
    )
    parser.add_argument(
        "--schema",
        default="",
        help="Schema string to write (default: empty string)",
    )
    parser.add_argument(
        "--type",
        default="sfw",
        dest="item_type",
        help='info.type to write for each item (default: "sfw")',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.csv_path.exists():
        raise FileNotFoundError(args.csv_path)

    out_path: Path = args.out
    if out_path is None:
        out_path = args.csv_path.with_suffix(".json")

    count = convert_csv_to_json(
        args.csv_path,
        out_path,
        schema=args.schema,
        item_type=args.item_type,
    )
    print(f"Wrote {out_path.as_posix()} ({count} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
