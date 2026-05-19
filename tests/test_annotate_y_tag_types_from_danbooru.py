# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.other.annotate_y_tag_types_from_danbooru import (
    annotate_payload,
    collect_unique_tag_texts,
    fetch_danbooru_tag_categories,
    normalize_tag_for_danbooru,
)


class _FakeResponse:
    def __init__(self, payload: list[dict[str, object]], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def json(self) -> list[dict[str, object]]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str],
        timeout: float,
    ) -> _FakeResponse:
        self.calls.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return _FakeResponse(
            [
                {"name": "wlop", "category": 1},
                {"name": "furry", "category": 0},
            ]
        )


def test_normalize_tag_for_danbooru_unescapes_prompt_text() -> None:
    assert normalize_tag_for_danbooru(r"Kamisato Ayaka \(Genshin\)") == (
        "kamisato_ayaka_(genshin)"
    )


def test_collect_unique_tag_texts_deduplicates_by_normalized_name() -> None:
    payload: dict[str, object] = {
        "items": [
            {
                "tags": [
                    {"text": "WLOP", "weight": 1.0},
                    {"text": "wlop", "weight": 1.1},
                    {"text": "furry", "weight": 1.0},
                ],
                "info": {"index": 0, "type": "artists"},
            }
        ]
    }

    assert collect_unique_tag_texts(payload) == ["WLOP", "furry"]


def test_annotate_payload_sets_tag_type_and_removes_info_type() -> None:
    payload: dict[str, object] = {
        "schema": "prompt-y-table/v2",
        "items": [
            {
                "tags": [
                    {"text": "wlop", "weight": 1.1},
                    {"text": "furry", "weight": 1.0},
                    {"text": "unknown tag", "weight": 1.0},
                ],
                "info": {"index": 433, "type": "artists"},
            }
        ],
    }

    summary = annotate_payload(payload, {"wlop": 1, "furry": 0})

    assert payload["schema"] == "prompt-y-table/v3"
    item = cast(dict[str, Any], cast(list[object], payload["items"])[0])
    assert item["info"] == {"index": 433}
    assert item["tags"] == [
        {"text": "wlop", "weight": 1.1, "type": "artists"},
        {"text": "furry", "weight": 1.0, "type": "general"},
        {"text": "unknown tag", "weight": 1.0, "type": "general"},
    ]
    assert summary.artist_reference_count == 1
    assert summary.general_reference_count == 2
    assert summary.missing_unique_count == 1


def test_fetch_danbooru_tag_categories_uses_name_normalize() -> None:
    session = _FakeSession()

    result = fetch_danbooru_tag_categories(
        ["WLOP", "furry"],
        base_url="https://example.test",
        request_interval_s=0,
        session=cast(requests.Session, cast(object, session)),
    )

    assert result == {"wlop": 1, "furry": 0}
    assert session.calls == [
        {
            "url": "https://example.test/tags.json",
            "params": {
                "search[name_normalize]": "wlop,furry",
                "limit": "2",
            },
            "headers": {"User-Agent": "sd-style-lab-tag-annotator/1.0"},
            "timeout": 20.0,
        }
    ]
