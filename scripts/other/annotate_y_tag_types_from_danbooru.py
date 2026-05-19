from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import cast

import requests
import yaml


if __package__ in {None, ""}:
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


DANBOORU_BASE_URL = "https://danbooru.donmai.us"
PROMPT_Y_SCHEMA = "prompt-y-table/v3"
ARTIST_CATEGORY = 1
TAG_TYPE_GENERAL = "general"
TAG_TYPE_ARTISTS = "artists"
VALID_TAG_TYPES = {TAG_TYPE_GENERAL, TAG_TYPE_ARTISTS}
DEFAULT_USER_AGENT = "sd-style-lab-tag-annotator/1.0"
_ESCAPED_CHAR_RE = re.compile(r"\\(.)")
_WHITESPACE_RE = re.compile(r"\s+")


class _IndentedDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow, False)


@dataclass(frozen=True, slots=True)
class AnnotationSummary:
    item_count: int
    tag_reference_count: int
    unique_tag_count: int
    artist_reference_count: int
    general_reference_count: int
    missing_unique_count: int


def normalize_tag_for_danbooru(text: str) -> str:
    unescaped = _ESCAPED_CHAR_RE.sub(r"\1", text.strip())
    return _WHITESPACE_RE.sub("_", unescaped.lower())


def collect_unique_tag_texts(payload: dict[str, object]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for _item_index, item in _iter_items(payload):
        tags_obj = item.get("tags")
        if not isinstance(tags_obj, list):
            raise ValueError("Y prompt 资产 items[].tags 必须为列表")

        tags = cast(list[object], tags_obj)
        for tag_obj in tags:
            if not isinstance(tag_obj, dict):
                raise ValueError("Y prompt 资产 tags[] 必须为对象")
            tag = cast(dict[str, object], tag_obj)
            text_obj = tag.get("text")
            if not isinstance(text_obj, str) or not text_obj.strip():
                raise ValueError("Y prompt 资产 tags[].text 必须为非空字符串")
            normalized = normalize_tag_for_danbooru(text_obj)
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(text_obj)

    return result


def annotate_payload(
    payload: dict[str, object],
    category_by_normalized_name: dict[str, int],
) -> AnnotationSummary:
    payload["schema"] = PROMPT_Y_SCHEMA

    item_count = 0
    tag_reference_count = 0
    artist_reference_count = 0
    general_reference_count = 0
    referenced_normalized: set[str] = set()

    for _item_index, item in _iter_items(payload):
        item_count += 1
        info_obj = item.get("info")
        if not isinstance(info_obj, dict):
            raise ValueError("Y prompt 资产 items[].info 必须为对象")
        info = cast(dict[str, object], info_obj)
        index_obj = info.get("index")
        if isinstance(index_obj, bool) or not isinstance(index_obj, int):
            raise ValueError("Y prompt 资产 items[].info.index 必须为整数")
        info.pop("type", None)

        tags_obj = item.get("tags")
        if not isinstance(tags_obj, list):
            raise ValueError("Y prompt 资产 items[].tags 必须为列表")

        tags = cast(list[object], tags_obj)
        for tag_obj in tags:
            if not isinstance(tag_obj, dict):
                raise ValueError("Y prompt 资产 tags[] 必须为对象")
            tag = cast(dict[str, object], tag_obj)
            text_obj = tag.get("text")
            if not isinstance(text_obj, str) or not text_obj.strip():
                raise ValueError("Y prompt 资产 tags[].text 必须为非空字符串")
            weight_obj = tag.get("weight")
            if isinstance(weight_obj, bool) or not isinstance(weight_obj, (int, float)):
                raise ValueError("Y prompt 资产 tags[].weight 必须为数字")

            normalized = normalize_tag_for_danbooru(text_obj)
            referenced_normalized.add(normalized)
            tag_type = (
                TAG_TYPE_ARTISTS
                if category_by_normalized_name.get(normalized) == ARTIST_CATEGORY
                else TAG_TYPE_GENERAL
            )
            tag["type"] = tag_type
            tag_reference_count += 1
            if tag_type == TAG_TYPE_ARTISTS:
                artist_reference_count += 1
            else:
                general_reference_count += 1

    found_normalized = {
        name for name in referenced_normalized if name in category_by_normalized_name
    }
    return AnnotationSummary(
        item_count=item_count,
        tag_reference_count=tag_reference_count,
        unique_tag_count=len(referenced_normalized),
        artist_reference_count=artist_reference_count,
        general_reference_count=general_reference_count,
        missing_unique_count=len(referenced_normalized - found_normalized),
    )


def fetch_danbooru_tag_categories(
    tag_texts: list[str],
    *,
    base_url: str = DANBOORU_BASE_URL,
    timeout_s: float = 20.0,
    request_interval_s: float = 0.12,
    batch_size: int = 100,
    max_retries: int = 2,
    user_agent: str = DEFAULT_USER_AGENT,
    session: requests.Session | None = None,
) -> dict[str, int]:
    if batch_size <= 0:
        raise ValueError("--batch-size 必须 > 0")
    if timeout_s <= 0:
        raise ValueError("--timeout 必须 > 0")
    if request_interval_s < 0:
        raise ValueError("--request-interval 必须 >= 0")
    if max_retries < 0:
        raise ValueError("--max-retries 必须 >= 0")

    normalized_names = [normalize_tag_for_danbooru(text) for text in tag_texts]
    normalized_names = list(dict.fromkeys(name for name in normalized_names if name))
    result: dict[str, int] = {}
    client = session or requests.Session()
    url = f"{base_url.rstrip('/')}/tags.json"

    for offset in range(0, len(normalized_names), batch_size):
        batch = normalized_names[offset : offset + batch_size]
        response_payload = _request_tag_batch(
            client,
            url=url,
            batch=batch,
            timeout_s=timeout_s,
            max_retries=max_retries,
            user_agent=user_agent,
        )
        for record_obj in response_payload:
            if not isinstance(record_obj, dict):
                continue
            record = cast(dict[str, object], record_obj)
            name_obj = record.get("name")
            category_obj = record.get("category")
            if not isinstance(name_obj, str):
                continue
            if isinstance(category_obj, bool) or not isinstance(category_obj, int):
                continue
            result[normalize_tag_for_danbooru(name_obj)] = category_obj

        if request_interval_s and offset + batch_size < len(normalized_names):
            sleep(request_interval_s)

    return result


def load_yaml_payload(path: Path) -> dict[str, object]:
    payload_obj = cast(object, yaml.safe_load(path.read_text(encoding="utf-8")))
    if not isinstance(payload_obj, dict):
        raise ValueError("Y prompt 资产顶层必须为对象")
    return cast(dict[str, object], payload_obj)


def write_yaml_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(
            payload,
            Dumper=_IndentedDumper,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Annotate prompt Y YAML tags with Danbooru tag categories."
    )
    parser.add_argument("yaml_path", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--in-place", action="store_true", dest="in_place")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--base-url", default=DANBOORU_BASE_URL)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--request-interval", type=float, default=0.12)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.in_place and args.out is not None:
        raise ValueError("--in-place 和 --out 只能选择一个")
    if not args.dry_run and not args.in_place and args.out is None:
        raise ValueError("写入时必须指定 --in-place 或 --out")
    if not args.yaml_path.exists():
        raise FileNotFoundError(args.yaml_path)

    payload = load_yaml_payload(args.yaml_path)
    unique_tag_texts = collect_unique_tag_texts(payload)
    categories = fetch_danbooru_tag_categories(
        unique_tag_texts,
        base_url=args.base_url,
        timeout_s=args.timeout,
        request_interval_s=args.request_interval,
        batch_size=args.batch_size,
        max_retries=args.max_retries,
        user_agent=args.user_agent,
    )
    summary = annotate_payload(payload, categories)

    out_path: Path | None = None
    if args.in_place:
        out_path = args.yaml_path
    elif args.out is not None:
        out_path = args.out

    if args.dry_run:
        print(_format_summary(summary, output_path=None))
        return 0

    assert out_path is not None
    write_yaml_payload(out_path, payload)
    print(_format_summary(summary, output_path=out_path))
    return 0


def _iter_items(
    payload: dict[str, object],
) -> list[tuple[int, dict[str, object]]]:
    items_obj = payload.get("items")
    if not isinstance(items_obj, list):
        raise ValueError("Y prompt 资产 items 必须为列表")

    result: list[tuple[int, dict[str, object]]] = []
    items = cast(list[object], items_obj)
    for index, item_obj in enumerate(items):
        if not isinstance(item_obj, dict):
            raise ValueError("Y prompt 资产 items[] 必须为对象")
        result.append((index, cast(dict[str, object], item_obj)))
    return result


def _request_tag_batch(
    session: requests.Session,
    *,
    url: str,
    batch: list[str],
    timeout_s: float,
    max_retries: int,
    user_agent: str,
) -> list[object]:
    params = {
        "search[name_normalize]": ",".join(batch),
        "limit": str(max(len(batch), 1)),
    }
    headers = {"User-Agent": user_agent}

    for attempt in range(max_retries + 1):
        response = session.get(url, params=params, headers=headers, timeout=timeout_s)
        if response.status_code == 429 and attempt < max_retries:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            sleep(retry_after if retry_after is not None else 1.0 + attempt)
            continue
        response.raise_for_status()
        payload_obj = cast(object, response.json())
        if not isinstance(payload_obj, list):
            raise ValueError("Danbooru /tags.json 返回值必须为列表")
        return cast(list[object], payload_obj)

    raise RuntimeError("Danbooru 请求重试次数已耗尽")


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _format_summary(
    summary: AnnotationSummary,
    *,
    output_path: Path | None,
) -> str:
    output = output_path.as_posix() if output_path is not None else "(dry-run)"
    return (
        f"Output: {output}\n"
        f"Items: {summary.item_count}\n"
        f"Tag references: {summary.tag_reference_count}\n"
        f"Unique tags: {summary.unique_tag_count}\n"
        f"Artist references: {summary.artist_reference_count}\n"
        f"General references: {summary.general_reference_count}\n"
        f"Missing unique tags: {summary.missing_unique_count}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
