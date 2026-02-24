from __future__ import annotations


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
