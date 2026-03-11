from __future__ import annotations

import re
from pathlib import Path
from typing import Final

RUN_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_run_key(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"字段 {field_name} 必须是非空字符串")
    if not RUN_KEY_RE.fullmatch(normalized):
        raise ValueError(
            f"字段 {field_name} 必须匹配 slug（仅允许小写字母、数字、连字符）: {normalized}"
        )
    return normalized


def validate_run_dir_path(run_dir: Path) -> str:
    return validate_run_key(run_dir.name, field_name="run_dir")
