import hashlib
import yaml
import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast


MAX_SEED = 18446744073709519872
X_INFO_TYPE_KEY = "_x_info_type"
Y_PROMPT_SCHEMA = "prompt-y-table/v3"
Y_TAG_TYPE_GENERAL = "general"
Y_TAG_TYPE_ARTISTS = "artists"
Y_TAG_TYPES = {Y_TAG_TYPE_GENERAL, Y_TAG_TYPE_ARTISTS}
Y_STYLE_KEY = "_y_style_key"
Y_COLLECTION_ID = "_y_collection_id"
Y_ITEM_INDEX = "_y_item_index"
ARTIST_WEIGHT_PROFILE_IDENTITY = "identity"
ARTIST_WEIGHT_PROFILE_SQUARE = "square"
ARTIST_WEIGHT_PROFILES = {
    ARTIST_WEIGHT_PROFILE_IDENTITY,
    ARTIST_WEIGHT_PROFILE_SQUARE,
}

PROMPT_TEMPLATE_ORDER = (
    "quality",
    "gender",
    "characters",
    "series",
    "rating",
    "y",
    "general",
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
    return ", ".join(tokens) + ", "


def _render_weighted_tag(tag: str, weight: float) -> str:
    if abs(weight - 1.0) < 1e-9:
        return tag
    return f"({tag}:{_format_weight(weight)})"


def read_x_rows(path: str | Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    payload_obj = cast(object, yaml.safe_load(Path(path).read_text(encoding="utf-8")))
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
        if "quality" in tags:
            raise ValueError(
                "X prompt 资产中的 tags.quality 已移除；请改用 generation.quality_prompt"
            )
        info_obj = item.get("info")
        info = cast(dict[str, object], info_obj) if isinstance(info_obj, dict) else {}

        mapped_row: dict[str, str] = {}
        for key in ["gender", "characters", "series", "rating", "general"]:
            mapped_row[key] = _render_weighted_tags(tags.get(key, []))

        info_type_obj = info.get("type")
        if isinstance(info_type_obj, str):
            mapped_row[X_INFO_TYPE_KEY] = info_type_obj.strip()
        else:
            mapped_row[X_INFO_TYPE_KEY] = ""

        rows.append(mapped_row)
    return rows


def read_x_descriptions(path: str | Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    payload_obj = cast(object, yaml.safe_load(Path(path).read_text(encoding="utf-8")))
    if not isinstance(payload_obj, dict):
        return rows

    payload = cast(dict[str, object], payload_obj)
    items = payload.get("items")
    if not isinstance(items, list):
        return rows

    items_list = cast(list[object], items)
    for item_obj in items_list:
        if not isinstance(item_obj, dict):
            rows.append({"zh": "", "en": ""})
            continue

        item = cast(dict[str, object], item_obj)
        description_obj = item.get("description")
        description = (
            cast(dict[str, object], description_obj)
            if isinstance(description_obj, dict)
            else {}
        )

        zh_obj = description.get("zh")
        en_obj = description.get("en")

        zh = zh_obj.strip() if isinstance(zh_obj, str) else ""
        en = en_obj.strip() if isinstance(en_obj, str) else ""

        rows.append({"zh": zh, "en": en})

    return rows


def _load_y_items(path: str | Path) -> list[dict[str, object]]:
    payload_obj = _load_y_payload(path)
    if not isinstance(payload_obj, dict):
        raise ValueError("Y prompt 资产顶层必须为对象")

    payload = cast(dict[str, object], payload_obj)
    schema_obj = payload.get("schema")
    if schema_obj != Y_PROMPT_SCHEMA:
        raise ValueError(f"Y prompt 资产 schema 必须为 {Y_PROMPT_SCHEMA}")

    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("Y prompt 资产 items 必须为列表")

    result: list[dict[str, object]] = []
    items_list = cast(list[object], items)
    for index, item_obj in enumerate(items_list):
        if not isinstance(item_obj, dict):
            raise ValueError(f"Y prompt 资产 items[{index}] 必须为对象")

        item = cast(dict[str, object], item_obj)
        info_obj = item.get("info")
        if not isinstance(info_obj, dict):
            raise ValueError(f"Y prompt 资产 items[{index}].info 必须为对象")
        info = cast(dict[str, object], info_obj)
        if "type" in info:
            raise ValueError("Y prompt 资产 info.type 已移除，请迁移到 tags[].type")
        info_index = info.get("index")
        if isinstance(info_index, bool) or not isinstance(info_index, int):
            raise ValueError(f"Y prompt 资产 items[{index}].info.index 必须为整数")

        tags = item.get("tags")
        if not isinstance(tags, list):
            raise ValueError(f"Y prompt 资产 items[{index}].tags 必须为列表")

        result.append(item)
    return result


def _load_y_payload(path: str | Path) -> object:
    return cast(object, yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _y_collection_id(path: str | Path, payload: Mapping[str, object]) -> str:
    raw_collection_id = payload.get("collection_id")
    if isinstance(raw_collection_id, str):
        normalized = _normalize_collection_id(raw_collection_id)
        if normalized:
            return normalized

    stem = Path(path).stem
    normalized_stem = _normalize_collection_id(stem)
    return normalized_stem or "y-prompts"


def _normalize_collection_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return normalized.strip("-")


def _y_identity_fields(
    *,
    collection_id: str,
    item: Mapping[str, object],
) -> dict[str, str]:
    info_obj = item.get("info")
    info = cast(Mapping[str, object], info_obj) if isinstance(info_obj, Mapping) else {}
    item_index = info.get("index")
    if not isinstance(item_index, int) or isinstance(item_index, bool):
        return {}

    item_index_text = str(item_index)
    return {
        Y_COLLECTION_ID: collection_id,
        Y_ITEM_INDEX: item_index_text,
        Y_STYLE_KEY: f"{collection_id}:{item_index_text}",
    }


def _validated_y_tags(tags: object) -> list[tuple[str, float, str]]:
    if not isinstance(tags, list):
        raise ValueError("Y prompt 资产 tags 必须为列表")

    result: list[tuple[str, float, str]] = []
    tags_list = cast(list[object], tags)
    for index, item_obj in enumerate(tags_list):
        if not isinstance(item_obj, dict):
            raise ValueError(f"Y prompt 资产 tags[{index}] 必须为对象")
        item = cast(dict[str, object], item_obj)
        text = item.get("text")
        if not isinstance(text, str):
            raise ValueError(f"Y prompt 资产 tags[{index}].text 必须为字符串")
        tag = text.strip()
        if not tag:
            raise ValueError(f"Y prompt 资产 tags[{index}].text 不能为空")

        weight_obj = item.get("weight")
        if isinstance(weight_obj, bool) or not isinstance(weight_obj, (int, float)):
            raise ValueError(f"Y prompt 资产 tags[{index}].weight 必须为数字")
        weight = float(weight_obj)

        type_obj = item.get("type")
        if not isinstance(type_obj, str):
            raise ValueError(f"Y prompt 资产 tags[{index}].type 必须为字符串")
        tag_type = type_obj.strip()
        if tag_type not in Y_TAG_TYPES:
            allowed = ", ".join(sorted(Y_TAG_TYPES))
            raise ValueError(
                f"Y prompt 资产 tags[{index}].type 必须为以下之一: {allowed}"
            )

        result.append((tag, weight, tag_type))
    return result


def _transform_artist_weight(weight: float, *, profile: str) -> float:
    if profile == ARTIST_WEIGHT_PROFILE_IDENTITY:
        return weight
    if profile == ARTIST_WEIGHT_PROFILE_SQUARE:
        return weight * weight
    allowed = ", ".join(sorted(ARTIST_WEIGHT_PROFILES))
    raise ValueError(f"artist_weight_profile 必须是以下之一: {allowed}")


def _render_y_weighted_tags(
    tags: object,
    *,
    artist_prefix: str = "",
    artist_weight_profile: str = ARTIST_WEIGHT_PROFILE_IDENTITY,
) -> str:
    tokens: list[str] = []
    for tag, weight, tag_type in _validated_y_tags(tags):
        rendered_weight = _transform_artist_weight(weight, profile=artist_weight_profile)
        rendered_tag = (
            f"{artist_prefix}{tag}"
            if artist_prefix and tag_type == Y_TAG_TYPE_ARTISTS
            else tag
        )
        tokens.append(_render_weighted_tag(rendered_tag, rendered_weight))

    if not tokens:
        return ""
    return ", ".join(tokens) + ", "


def _render_novelai_weighted_tags(tags: object) -> str:
    """Render YAML tags directly as NovelAI native format."""
    tokens: list[str] = []
    for tag, weight, tag_type in _validated_y_tags(tags):
        prefixed = f"artist:{tag}" if tag_type == Y_TAG_TYPE_ARTISTS else tag

        if abs(weight - 1.0) < 1e-9:
            tokens.append(prefixed)
        else:
            weight_str = _format_weight(weight)
            tokens.append(f"{weight_str}::{prefixed} ::")

    if not tokens:
        return ""
    return ", ".join(tokens) + ", "


def read_y_rows_for_novelai(path: str | Path) -> list[dict[str, str]]:
    """Read Y-axis data and output NovelAI native format."""
    rows: list[dict[str, str]] = []

    payload_obj = _load_y_payload(path)
    if not isinstance(payload_obj, Mapping):
        raise ValueError("Y prompt 资产顶层必须为对象")
    payload = cast(Mapping[str, object], payload_obj)
    collection_id = _y_collection_id(path, payload)

    for item in _load_y_items(path):
        rows.append(
            {
                "y": _render_novelai_weighted_tags(item.get("tags", [])),
                **_y_identity_fields(collection_id=collection_id, item=item),
            }
        )
    return rows


def read_y_rows(
    path: str | Path,
    artists_column: str = "Artists",
    *,
    artist_prefix: str = "",
    artist_weight_profile: str = ARTIST_WEIGHT_PROFILE_IDENTITY,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    _ = artists_column

    payload_obj = _load_y_payload(path)
    if not isinstance(payload_obj, Mapping):
        raise ValueError("Y prompt 资产顶层必须为对象")
    payload = cast(Mapping[str, object], payload_obj)
    collection_id = _y_collection_id(path, payload)

    for item in _load_y_items(path):
        rows.append(
            {
                "y": _render_y_weighted_tags(
                    item.get("tags", []),
                    artist_prefix=artist_prefix,
                    artist_weight_profile=artist_weight_profile,
                ),
                **_y_identity_fields(collection_id=collection_id, item=item),
            }
        )
    return rows


def render_positive_prompt(
    x_row: Mapping[str, str], y_value: str, quality_prompt: str | None = None
) -> str:
    segments = {
        "quality": quality_prompt or "",
        "gender": x_row.get("gender", ""),
        "characters": x_row.get("characters", ""),
        "series": x_row.get("series", ""),
        "rating": x_row.get("rating", ""),
        "y": y_value,
        "general": x_row.get("general", ""),
    }
    rendered: list[str] = []
    for key in PROMPT_TEMPLATE_ORDER:
        segment = segments[key].strip()
        if not segment:
            continue
        segment = segment.rstrip(", ").rstrip() + ", "
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
    quality_prompt: str | None = None,
) -> dict[str, str | int]:
    y_value = y_row if isinstance(y_row, str) else y_row.get("y", "")
    positive_prompt = render_positive_prompt(x_row, y_value, quality_prompt)
    return {
        "positive_prompt": positive_prompt,
        "prompt_hash": compute_prompt_hash(positive_prompt),
        "seed": derive_seed(base_seed, x_index, y_index),
    }
