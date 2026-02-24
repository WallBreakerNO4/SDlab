from __future__ import annotations

from dataclasses import dataclass

from scripts.generation.prompt_grid import X_INFO_TYPE_KEY


@dataclass(slots=True)
class SelectedRow:
    index: int
    value: dict[str, str]


def _extract_x_info_type(x_row: dict[str, str]) -> str | None:
    value = x_row.get(X_INFO_TYPE_KEY)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _select_rows(
    rows: list[dict[str, str]],
    limit: int | None,
    indexes_raw: str | None,
    axis_name: str,
) -> list[SelectedRow]:
    indexed_rows = [
        SelectedRow(index=index, value=value) for index, value in enumerate(rows)
    ]

    indexes = _parse_indexes(indexes_raw, axis_name)
    if indexes is not None:
        selected: list[SelectedRow] = []
        for index in indexes:
            if index < 0 or index >= len(rows):
                raise ValueError(
                    f"--{axis_name}-indexes 包含越界索引: {index} (最大 {len(rows) - 1})"
                )
            selected.append(SelectedRow(index=index, value=rows[index]))
        indexed_rows = selected

    if limit is not None:
        indexed_rows = indexed_rows[:limit]

    return indexed_rows


def _select_rows_by_fixed_indexes(
    *,
    rows: list[dict[str, str]],
    indexes: list[int],
    axis_name: str,
) -> list[SelectedRow]:
    selected: list[SelectedRow] = []
    for index in indexes:
        if index < 0 or index >= len(rows):
            raise ValueError(
                f"run.json.selection.{axis_name}_indexes 包含越界索引: {index} (最大 {len(rows) - 1})"
            )
        selected.append(SelectedRow(index=index, value=rows[index]))
    return selected


def _parse_indexes(raw: str | None, axis_name: str) -> list[int] | None:
    if raw is None:
        return None

    tokens = [token.strip() for token in raw.split(",") if token.strip()]
    if not tokens:
        return []

    parsed: list[int] = []
    for token in tokens:
        if not token.isdigit():
            raise ValueError(f"--{axis_name}-indexes 仅支持非负整数列表: {raw}")
        parsed.append(int(token))

    unique: list[int] = []
    seen: set[int] = set()
    for value in parsed:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
