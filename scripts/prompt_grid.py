import csv
import hashlib
import re
from collections.abc import Mapping
from pathlib import Path


MAX_SEED = 18446744073709519872

X_COLUMN_MAPPING = {
    "Gender tags": "gender",
    "Character(s) tags": "characters",
    "Series tags": "series",
    "Rating tags": "rating",
    "General tags": "general",
    "Qulity tags": "quality",
}

PROMPT_TEMPLATE_ORDER = (
    "gender",
    "characters",
    "series",
    "rating",
    "y",
    "general",
    "quality",
)


def read_x_rows(csv_path: str | Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with Path(csv_path).open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for raw_row in reader:
            mapped_row: dict[str, str] = {}
            for source_col, target_key in X_COLUMN_MAPPING.items():
                value = raw_row.get(source_col, "")
                mapped_row[target_key] = "" if value is None else value
            rows.append(mapped_row)
    return rows


def read_y_rows(
    csv_path: str | Path, artists_column: str = "Artists"
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with Path(csv_path).open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for raw_row in reader:
            value = raw_row.get(artists_column, "")
            rows.append({"y": "" if value is None else value})
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
