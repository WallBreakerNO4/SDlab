from __future__ import annotations

import os


class MissingRequiredEnvError(ValueError):
    name: str

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class InvalidEnvIntError(ValueError):
    name: str

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise MissingRequiredEnvError(name)
    return value.strip()


def optional_env_int(name: str, *, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise InvalidEnvIntError(name) from exc
