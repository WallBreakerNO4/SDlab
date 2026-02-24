from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from scripts.generation.prompt_grid import render_positive_prompt


ALLOWED_TEMPLATE_KEYS = {
    "gender",
    "characters",
    "series",
    "rating",
    "y",
    "general",
    "quality",
}
TEMPLATE_TOKEN_RE = re.compile(r"\{([a-z_]+)\}")


def _build_example_prompt(
    template: str,
    x_selected: list[Any],
    y_selected: list[Any],
    *,
    render_prompt_by_template: Callable[[str, dict[str, str], str], str],
) -> str:
    if not x_selected or not y_selected:
        return ""

    first_x_obj = x_selected[0]
    first_y_obj = y_selected[0]
    first_x = getattr(first_x_obj, "value")
    first_y = getattr(first_y_obj, "value").get("y", "")
    return render_prompt_by_template(template, first_x, first_y)


def _render_prompt_by_template(
    template: str,
    x_row: dict[str, str],
    y_value: str,
    *,
    default_template: str,
) -> str:
    if template == default_template:
        return render_positive_prompt(x_row, y_value)

    key_map = {
        "gender": x_row.get("gender", ""),
        "characters": x_row.get("characters", ""),
        "series": x_row.get("series", ""),
        "rating": x_row.get("rating", ""),
        "y": y_value,
        "general": x_row.get("general", ""),
        "quality": x_row.get("quality", ""),
    }

    stripped = TEMPLATE_TOKEN_RE.sub("", template)
    if stripped.strip():
        raise ValueError("--template 仅支持由占位符组成，例如 {gender}{y}{quality}")

    rendered: list[str] = []
    for match in TEMPLATE_TOKEN_RE.finditer(template):
        key = match.group(1)
        if key not in ALLOWED_TEMPLATE_KEYS:
            raise ValueError(f"--template 包含未知占位符: {{{key}}}")
        segment = key_map[key].strip()
        if not segment:
            continue
        if not segment.endswith(","):
            segment = f"{segment},"
        rendered.append(segment)
    return "".join(rendered)
