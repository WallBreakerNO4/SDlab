from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


UP_BASE = 1.1
DOWN_BASE = 0.9


def _is_escaped(text: str, pos: int) -> bool:
    backslashes = 0
    i = pos - 1
    while i >= 0 and text[i] == "\\":
        backslashes += 1
        i -= 1
    return (backslashes % 2) == 1


def _depth_weight(base: float, depth: int) -> float:
    if depth <= 0:
        return 1.0
    return math.pow(base, depth)


def _current_weight(paren_depth: int, bracket_depth: int) -> float:
    return _depth_weight(UP_BASE, paren_depth) * _depth_weight(DOWN_BASE, bracket_depth)


def parse_weighted_tags(prompt: str) -> list[dict[str, object]]:
    text = prompt.strip()
    if not text:
        return []

    items: list[dict[str, object]] = []
    buf: list[str] = []
    paren_depth = 0
    bracket_depth = 0

    def flush() -> None:
        token = "".join(buf).strip()
        buf.clear()
        if not token:
            return
        weight = round(_current_weight(paren_depth, bracket_depth), 3)
        items.append({"text": token, "weight": weight})

    for i, ch in enumerate(text):
        if (ch == "," or ch == "，") and not _is_escaped(text, i):
            flush()
            continue

        if ch == "(" and not _is_escaped(text, i):
            flush()
            paren_depth += 1
            continue

        if ch == ")" and not _is_escaped(text, i):
            if paren_depth > 0:
                flush()
                paren_depth -= 1
            else:
                pass
            continue

        if ch == "[" and not _is_escaped(text, i):
            flush()
            bracket_depth += 1
            continue

        if ch == "]" and not _is_escaped(text, i):
            if bracket_depth > 0:
                flush()
                bracket_depth -= 1
            else:
                pass
            continue

        buf.append(ch)

    flush()
    return items


def convert_csv_to_json(
    csv_path: Path,
    out_path: Path,
    *,
    schema: str,
    tags_column: str,
    index_column: str,
    item_type: str,
) -> int:
    items: list[dict[str, object]] = []

    with csv_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            index_raw = row.get(index_column)
            if index_raw is None:
                raise ValueError(
                    f"Missing column {index_column!r} in {csv_path.as_posix()}"
                )
            index_str = index_raw.strip()
            if not index_str:
                raise ValueError(
                    f"Empty {index_column!r} value in {csv_path.as_posix()}"
                )
            index = int(index_str)

            tags_raw = row.get(tags_column, "")
            tags_str = "" if tags_raw is None else tags_raw
            tags = parse_weighted_tags(tags_str)

            items.append(
                {
                    "tags": tags,
                    "info": {"index": index, "type": item_type},
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
        description="Convert prompt Y CSV files to JSON assets."
    )
    parser.add_argument(
        "csv_paths",
        nargs="+",
        type=Path,
        help="One or more CSV files to convert",
    )
    parser.add_argument(
        "--schema",
        default="prompt-y-table/v2",
        help='Schema string to write (default: "prompt-y-table/v2")',
    )
    parser.add_argument(
        "--type",
        default="artists",
        dest="item_type",
        help='info.type to write for each item (default: "artists")',
    )
    parser.add_argument(
        "--index-column",
        default="Index",
        help='CSV column name for info.index (default: "Index")',
    )
    parser.add_argument(
        "--tags-column",
        default="Artists",
        help='CSV column name to split into tags list (default: "Artists")',
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Optional directory to place output JSON files; default writes next to CSV",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    for csv_path in args.csv_paths:
        if not csv_path.exists():
            raise FileNotFoundError(csv_path)
        out_dir: Path = csv_path.parent if args.out_dir is None else args.out_dir
        out_path = out_dir / (csv_path.stem + ".json")
        count = convert_csv_to_json(
            csv_path,
            out_path,
            schema=args.schema,
            tags_column=args.tags_column,
            index_column=args.index_column,
            item_type=args.item_type,
        )
        print(f"Wrote {out_path.as_posix()} ({count} items)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
