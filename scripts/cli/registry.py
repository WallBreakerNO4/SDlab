from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
import importlib
from types import MappingProxyType
from typing import cast

ScriptMain = Callable[[list[str] | None], int]


@dataclass(frozen=True, slots=True)
class MenuEntry:
    key: str
    label: str
    entrypoint: str
    enabled: bool = True


_DEFAULT_ENTRIES: tuple[MenuEntry, ...] = (
    MenuEntry(
        key="generate_grid",
        label="Generate ComfyUI grid",
        entrypoint="scripts.generation.comfyui_part1_generate:main",
    ),
    MenuEntry(
        key="convert_x_csv",
        label="Convert X CSV to JSON",
        entrypoint="scripts.other.convert_x_csv_to_json:main",
    ),
    MenuEntry(
        key="convert_y_csv",
        label="Convert Y CSV to JSON",
        entrypoint="scripts.other.convert_y_csv_to_json:main",
    ),
    MenuEntry(
        key="upload_r2",
        label="Upload images to R2",
        entrypoint="scripts.r2_upload.upload_images_to_r2:main",
    ),
)

_BY_KEY = MappingProxyType({entry.key: entry for entry in _DEFAULT_ENTRIES})


def iter_entries(*, include_disabled: bool = True) -> Iterator[MenuEntry]:
    for entry in _DEFAULT_ENTRIES:
        if not include_disabled and not entry.enabled:
            continue
        yield entry


def get_entry(key: str) -> MenuEntry:
    entry = _BY_KEY.get(key)
    if entry is None:
        raise KeyError(f"Unknown menu key: {key}")
    return entry


def load_entrypoint(entry: MenuEntry | str) -> ScriptMain:
    target = entry.entrypoint if isinstance(entry, MenuEntry) else entry
    module_name, sep, func_name = target.partition(":")
    if sep != ":" or not module_name or not func_name:
        raise ValueError(f"Invalid entrypoint: {target}")

    module = importlib.import_module(module_name)
    func = getattr(module, func_name, None)
    if not callable(func):
        raise TypeError(f"Entrypoint is not callable: {target}")

    return cast(ScriptMain, func)
