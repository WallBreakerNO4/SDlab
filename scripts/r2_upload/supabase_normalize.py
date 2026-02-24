from __future__ import annotations
import hashlib
from collections.abc import Mapping
from typing import cast


class PayloadValidationError(ValueError):
    field: str
    expected: str

    def __init__(self, message: str, *, field: str, expected: str) -> None:
        super().__init__(message)
        self.field = field
        self.expected = expected


def required_str(data: Mapping[str, object], field: str) -> str:
    raw = data.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise PayloadValidationError(
            "payload field must be a non-empty string",
            field=field,
            expected="str",
        )
    return raw.strip()


def required_int(data: Mapping[str, object], field: str) -> int:
    raw = data.get(field)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise PayloadValidationError(
            "payload field must be an integer",
            field=field,
            expected="int",
        )
    return raw


def int_with_default(data: Mapping[str, object], field: str, *, default: int) -> int:
    raw = data.get(field)
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise PayloadValidationError(
            "payload field must be an integer",
            field=field,
            expected="int",
        )
    return raw


def required_json_object(
    data: Mapping[str, object], field: str
) -> Mapping[str, object]:
    raw = data.get(field)
    if not isinstance(raw, Mapping):
        raise PayloadValidationError(
            "payload field must be a JSON object",
            field=field,
            expected="object",
        )
    return cast(Mapping[str, object], raw)


def optional_object_list(value: object, *, field: str) -> list[Mapping[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise PayloadValidationError(
            "payload field must be an array",
            field=field,
            expected="array",
        )
    result: list[Mapping[str, object]] = []
    for item in cast(list[object], value):
        if not isinstance(item, Mapping):
            raise PayloadValidationError(
                "array item must be an object",
                field=field,
                expected="object[]",
            )
        result.append(cast(Mapping[str, object], item))
    return result


def optional_int(value: object, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise PayloadValidationError(
            "payload field must be an integer",
            field=field,
            expected="int|null",
        )
    return value


def optional_str(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PayloadValidationError(
            "payload field must be a string",
            field=field,
            expected="str|null",
        )
    trimmed = value.strip()
    return trimmed if trimmed else None


def extract_id_from_data(data: object) -> str | None:
    if not isinstance(data, list) or not data:
        return None
    first_obj = cast(list[object], data)[0]
    if not isinstance(first_obj, Mapping):
        return None
    value = cast(Mapping[str, object], first_obj).get("id")
    if not isinstance(value, str) or not value:
        return None
    return value


def extract_rows_from_data(data: object) -> list[Mapping[str, object]]:
    if not isinstance(data, list):
        return []
    rows: list[Mapping[str, object]] = []
    for item in cast(list[object], data):
        if isinstance(item, Mapping):
            rows.append(cast(Mapping[str, object], item))
    return rows


def extract_remote_code(exc: Exception) -> str | None:
    raw_code = getattr(exc, "code", None)
    if isinstance(raw_code, str) and raw_code.strip():
        return raw_code.strip()
    raw_status = getattr(exc, "status", None)
    if isinstance(raw_status, int) and raw_status > 0:
        return f"http_{raw_status}"
    return None


def hash12(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def normalize_rows_for_postgrest(
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not rows:
        return []
    ordered_keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                ordered_keys.append(key)
                seen.add(key)

    normalized: list[dict[str, object]] = []
    for row in rows:
        normalized_row: dict[str, object] = {}
        for key in ordered_keys:
            normalized_row[key] = row.get(key)
        normalized.append(normalized_row)
    return normalized
