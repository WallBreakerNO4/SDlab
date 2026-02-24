from __future__ import annotations

import os

from dotenv import find_dotenv, load_dotenv


def _autoload_dotenv() -> None:
    dotenv_path = find_dotenv(filename=".env", usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path=dotenv_path, encoding="utf-8")
        return
    return


def _env_str(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _env_float(name: str, default: float) -> float:
    raw = _env_str(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 不是有效浮点数: {raw}") from exc


def _env_optional_float(name: str) -> float | None:
    raw = _env_str(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 不是有效浮点数: {raw}") from exc


def _env_optional_int(name: str) -> int | None:
    raw = _env_str(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 不是有效整数: {raw}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = _env_str(name)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(
        f"环境变量 {name} 不是有效布尔值: {raw} (可用: 1/0 true/false yes/no on/off)"
    )


def _resolve_append_negative_prompt(raw: str | None) -> str | None:
    DEFAULT_APPEND = "nsfw, nipples, pussy, nude,"

    if raw is None:
        return DEFAULT_APPEND

    stripped = raw.strip()
    if not stripped:
        return None

    return stripped


def _env_append_negative_prompt() -> str | None:
    raw = os.getenv("COMFYUI_APPEND_NEGATIVE_PROMPT")
    return _resolve_append_negative_prompt(raw)
