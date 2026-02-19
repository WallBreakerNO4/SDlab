import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast


MAX_SEED = 18446744073709519872

PROMPT_TEMPLATE_ORDER = (
    "gender",
    "characters",
    "series",
    "rating",
    "y",
    "general",
    "quality",
)


def _format_weight(weight: float) -> str:
    rendered = f"{weight:.3f}".rstrip("0").rstrip(".")
    return rendered or "0"


def _render_weighted_tags(tags: object) -> str:
    if not isinstance(tags, list):
        return ""

    tokens: list[str] = []
    tags_list = cast(list[object], tags)
    for item_obj in tags_list:
        if not isinstance(item_obj, dict):
            continue
        item = cast(dict[str, object], item_obj)
        text = item.get("text")
        if not isinstance(text, str):
            continue
        tag = text.strip()
        if not tag:
            continue

        weight_obj = item.get("weight", 1.0)
        weight: float
        if isinstance(weight_obj, (int, float)):
            weight = float(weight_obj)
        else:
            weight = 1.0

        if abs(weight - 1.0) < 1e-9:
            tokens.append(tag)
        else:
            tokens.append(f"({tag}:{_format_weight(weight)})")

    if not tokens:
        return ""
    return ",".join(tokens) + ","


def read_x_rows(path: str | Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    payload_obj = cast(object, json.loads(Path(path).read_text(encoding="utf-8")))
    if not isinstance(payload_obj, dict):
        return rows

    payload = cast(dict[str, object], payload_obj)
    items = payload.get("items")
    if not isinstance(items, list):
        return rows

    items_list = cast(list[object], items)
    for item_obj in items_list:
        if not isinstance(item_obj, dict):
            continue
        item = cast(dict[str, object], item_obj)
        tags_obj = item.get("tags")
        tags = cast(dict[str, object], tags_obj) if isinstance(tags_obj, dict) else {}

        mapped_row: dict[str, str] = {}
        for key in ["gender", "characters", "series", "rating", "general", "quality"]:
            mapped_row[key] = _render_weighted_tags(tags.get(key, []))
        rows.append(mapped_row)
    return rows


def read_y_rows(
    path: str | Path, artists_column: str = "Artists"
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    _ = artists_column

    payload_obj = cast(object, json.loads(Path(path).read_text(encoding="utf-8")))
    if not isinstance(payload_obj, dict):
        return rows

    payload = cast(dict[str, object], payload_obj)
    items = payload.get("items")
    if not isinstance(items, list):
        return rows

    items_list = cast(list[object], items)
    for item_obj in items_list:
        if not isinstance(item_obj, dict):
            continue
        item = cast(dict[str, object], item_obj)
        rows.append({"y": _render_weighted_tags(item.get("tags", []))})
    return rows


def render_positive_prompt(x_row: Mapping[str, str], y_value: str) -> str:
    segments = {
        "gender": x_row.get("gender", ""),
        "characters": x_row.get("characters", ""),
        "series": x_row.get("series", ""),
        "rating": x_row.get("rating", ""),
        "y": y_value,
        "general": x_row.get("general", ""),
        "quality": x_row.get("quality", ""),
    }
    rendered: list[str] = []
    for key in PROMPT_TEMPLATE_ORDER:
        segment = segments[key].strip()
        if not segment:
            continue
        if not segment.endswith(","):
            segment = f"{segment},"
        rendered.append(segment)
    return "".join(rendered)


def normalize_prompt(prompt: str) -> str:
    normalized = prompt.strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    return normalized


def compute_prompt_hash(prompt: str) -> str:
    normalized = normalize_prompt(prompt)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def derive_seed(base_seed: int, x_index: int, y_index: int) -> int:
    raw = f"{base_seed}:{x_index}:{y_index}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return int(digest[:16], 16) % MAX_SEED


def build_prompt_cell(
    x_row: Mapping[str, str],
    y_row: Mapping[str, str] | str,
    base_seed: int,
    x_index: int,
    y_index: int,
) -> dict[str, str | int]:
    y_value = y_row if isinstance(y_row, str) else y_row.get("y", "")
    positive_prompt = render_positive_prompt(x_row, y_value)
    return {
        "positive_prompt": positive_prompt,
        "prompt_hash": compute_prompt_hash(positive_prompt),
        "seed": derive_seed(base_seed, x_index, y_index),
    }
