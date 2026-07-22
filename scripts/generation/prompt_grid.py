import hashlib
import json
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
Y_POSITIVE_VALUE = "_y_positive_value"
Y_ARTIST_CHAIN = "_y_artist_chain"
ARTIST_WEIGHT_PROFILE_IDENTITY = "identity"
ARTIST_WEIGHT_PROFILE_SQUARE = "square"
ARTIST_WEIGHT_PROFILES = {
    ARTIST_WEIGHT_PROFILE_IDENTITY,
    ARTIST_WEIGHT_PROFILE_SQUARE,
}

NEWBIE_X_SCHEMA = "newbie-x-table/v1"
NEWBIE_CHAR_SUBTAGS = (
    "n",
    "gender",
    "appearance",
    "clothing",
    "body_type",
    "expression",
    "action",
    "interaction",
    "position",
)
NEWBIE_GENERAL_SUBTAGS = (
    "count",
    "artists",
    "style",
    "background",
    "environment",
    "perspective",
    "atmosphere",
    "lighting",
    "quality",
    "objects",
    "other",
)

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


def _render_subtag(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return _render_weighted_tags(value).rstrip(", ")
    raise ValueError(f"NewBie X 子标签值只支持 str 或 list，收到 {type(value).__name__}")


def read_x_rows_newbie(path: str | Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    payload_obj = cast(object, yaml.safe_load(Path(path).read_text(encoding="utf-8")))
    if not isinstance(payload_obj, dict):
        return rows

    payload = cast(dict[str, object], payload_obj)
    schema_obj = payload.get("schema")
    if schema_obj != NEWBIE_X_SCHEMA:
        raise ValueError(f"NewBie X prompt 资产 schema 必须为 {NEWBIE_X_SCHEMA}")

    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("NewBie X prompt 资产 items 必须为列表")

    char_keys = set(NEWBIE_CHAR_SUBTAGS)
    general_keys = set(NEWBIE_GENERAL_SUBTAGS)

    items_list = cast(list[object], items)
    for item_obj in items_list:
        if not isinstance(item_obj, dict):
            continue
        item = cast(dict[str, object], item_obj)

        characters_obj = item.get("characters")
        if not isinstance(characters_obj, list):
            raise ValueError("NewBie X prompt 资产 characters 必须为列表")
        characters: list[dict[str, str]] = []
        for char_index, char_obj in enumerate(cast(list[object], characters_obj)):
            if not isinstance(char_obj, dict):
                raise ValueError(
                    f"NewBie X prompt 资产 characters[{char_index}] 必须为对象"
                )
            char = cast(dict[str, object], char_obj)
            mapped_char: dict[str, str] = {}
            for key, val in char.items():
                if key not in char_keys:
                    raise ValueError(
                        f"NewBie X prompt 资产 characters[{char_index}] 含未知子标签 {key!r}"
                    )
                mapped_char[key] = _render_subtag(val)
            characters.append(mapped_char)

        general_obj = item.get("general")
        if not isinstance(general_obj, dict):
            raise ValueError("NewBie X prompt 资产 general 必须为对象")
        general = cast(dict[str, object], general_obj)
        mapped_general: dict[str, str] = {}
        for key, val in general.items():
            if key not in general_keys:
                raise ValueError(f"NewBie X prompt 资产 general 含未知子标签 {key!r}")
            mapped_general[key] = _render_subtag(val)

        info_obj = item.get("info")
        info = cast(dict[str, object], info_obj) if isinstance(info_obj, dict) else {}
        info_type_obj = info.get("type")
        if isinstance(info_type_obj, str):
            info_type = info_type_obj.strip()
        else:
            info_type = ""

        caption_text = _read_newbie_caption(item)

        rows.append(
            {
                "characters": characters,
                "general": mapped_general,
                X_INFO_TYPE_KEY: info_type,
                "caption": caption_text,
            }
        )
    return rows


def _read_newbie_caption(item: dict[str, object]) -> str:
    """从 NewBie X 资产 item 读取 caption 自然语言描述。

    caption 为选填字段，支持两种写法：
    - dict 形式（含 zh/en）：默认取 en（英文模型对齐更佳），缺失则回退 zh；
    - 裸字符串简写：直接使用。
    缺失或为空时返回空串（不注入，回退到 workflow 原值）。
    """
    caption_obj = item.get("caption")
    if caption_obj is None:
        return ""
    if isinstance(caption_obj, dict):
        caption_map = cast(dict[str, object], caption_obj)
        cap_en = caption_map.get("en")
        if isinstance(cap_en, str) and cap_en.strip():
            return cap_en.strip()
        cap_zh = caption_map.get("zh")
        if isinstance(cap_zh, str) and cap_zh.strip():
            return cap_zh.strip()
        return ""
    if isinstance(caption_obj, str):
        return caption_obj.strip()
    raise ValueError(
        f"NewBie X caption 必须为 zh/en 对象或字符串，收到 {type(caption_obj).__name__}"
    )


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


def _render_anima_mixer_y_tags(
    tags: object,
    *,
    artist_weight_profile: str,
) -> tuple[str, str]:
    general_tokens: list[str] = []
    artist_tokens: list[str] = []
    for tag, weight, tag_type in _validated_y_tags(tags):
        rendered_weight = _transform_artist_weight(
            weight,
            profile=artist_weight_profile,
        )
        if tag_type == Y_TAG_TYPE_ARTISTS:
            artist = f"@{tag}"
            if abs(rendered_weight - 1.0) < 1e-9:
                artist_tokens.append(artist)
            else:
                artist_tokens.append(f"{_format_weight(rendered_weight)}::{artist}")
            continue
        general_tokens.append(_render_weighted_tag(tag, rendered_weight))

    positive_y = ", ".join(general_tokens)
    if positive_y:
        positive_y += ", "
    return positive_y, ", ".join(artist_tokens)


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
    anima_artist_mixer: bool = False,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    _ = artists_column

    payload_obj = _load_y_payload(path)
    if not isinstance(payload_obj, Mapping):
        raise ValueError("Y prompt 资产顶层必须为对象")
    payload = cast(Mapping[str, object], payload_obj)
    collection_id = _y_collection_id(path, payload)

    for item in _load_y_items(path):
        tags = item.get("tags", [])
        y_value = _render_y_weighted_tags(
            tags,
            artist_prefix=artist_prefix,
            artist_weight_profile=artist_weight_profile,
        )
        mixer_fields: dict[str, str] = {}
        if anima_artist_mixer:
            positive_y, artist_chain = _render_anima_mixer_y_tags(
                tags,
                artist_weight_profile=artist_weight_profile,
            )
            mixer_fields = {
                Y_POSITIVE_VALUE: positive_y,
                Y_ARTIST_CHAIN: artist_chain,
            }
        rows.append(
            {
                "y": y_value,
                **mixer_fields,
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


def _emit_xml_subtag(name: str, text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    return f"<{name}>{stripped}</{name}>"


_NEWBIE_SYSTEM_PROMPT = (
    "You are an assistant designed to generate high-quality anime images "
    "based on xml format prompts. <Prompt Start> "
)


def assemble_newbie_prompt(
    x_row: Mapping[str, object],
    y_value: str,
    quality_prompt: str | None = None,
) -> str:
    """拼装 NewBie 完整正向 prompt：system prompt + <image> 外壳 + caption + XML tags。

    与 render_positive_prompt_xml 不同，此函数产出可直接写入 CLIPTextEncode.text
    的完整字符串，无需依赖 ComfyUI 的 StringReplace 节点链路做运行时替换。
    """
    xml_tags = render_positive_prompt_xml(
        x_row, y_value, quality_prompt=quality_prompt
    )
    caption = str(x_row.get("caption") or "")
    return (
        f"{_NEWBIE_SYSTEM_PROMPT}\n"
        "<image>\n"
        f"<caption>{caption}</caption>\n"
        f"{xml_tags}\n"
        "</image>"
    )


def render_positive_prompt_xml(
    x_row: Mapping[str, object],
    y_value: str,
    quality_prompt: str | None = None,
) -> str:
    characters = x_row.get("characters", [])
    if not isinstance(characters, list):
        characters = []
    general = x_row.get("general", {})
    if not isinstance(general, Mapping):
        general = {}

    artists_text = ""
    if y_value.strip():
        artists_text = y_value.rstrip(", ").rstrip()
    elif general.get("artists", ""):
        artists_text = str(general.get("artists", "")).rstrip(", ").rstrip()

    quality_parts: list[str] = []
    if quality_prompt and quality_prompt.strip():
        quality_parts.append(quality_prompt.strip().rstrip(", ").rstrip())
    general_quality = general.get("quality", "")
    if general_quality and str(general_quality).strip():
        quality_parts.append(str(general_quality).strip().rstrip(", ").rstrip())
    quality_text = ", ".join(quality_parts).rstrip(", ").rstrip()

    blocks: list[str] = []
    for index, char in enumerate(cast(list[object], characters), start=1):
        if not isinstance(char, Mapping):
            continue
        lines: list[str] = []
        for subtag in NEWBIE_CHAR_SUBTAGS:
            lines.append(_emit_xml_subtag(subtag, str(char.get(subtag, ""))))
        char_body = "\n".join(line for line in lines if line)
        if char_body:
            blocks.append(f"<character_{index}>\n{char_body}\n</character_{index}>")

    general_lines: list[str] = []
    for subtag in NEWBIE_GENERAL_SUBTAGS:
        if subtag == "artists":
            general_lines.append(_emit_xml_subtag(subtag, artists_text))
        elif subtag == "quality":
            general_lines.append(_emit_xml_subtag(subtag, quality_text))
        else:
            general_lines.append(
                _emit_xml_subtag(subtag, str(general.get(subtag, "")))
            )
    general_body = "\n".join(line for line in general_lines if line)
    blocks.append(
        f"<general_tags>\n{general_body}\n</general_tags>"
        if general_body
        else "<general_tags>\n</general_tags>"
    )

    return "\n\n".join(blocks)


def normalize_prompt(prompt: str) -> str:
    normalized = prompt.strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    return normalized


def compute_prompt_hash(prompt: str, artist_chain: str | None = None) -> str:
    normalized = normalize_prompt(prompt)
    if artist_chain is None:
        hash_input = normalized
    else:
        hash_input = json.dumps(
            {
                "artist_chain": normalize_prompt(artist_chain),
                "positive_prompt": normalized,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


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
