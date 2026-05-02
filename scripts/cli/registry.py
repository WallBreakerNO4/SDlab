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
        label="生图 (ComfyUI)",
        entrypoint="scripts.generation.comfyui_part1_generate:main",
    ),
    MenuEntry(
        key="generate_novelai",
        label="生图 (NovelAI)",
        entrypoint="scripts.generation.novelai_generate:main",
    ),
    MenuEntry(
        key="convert_x_csv",
        label="X CSV 转 YAML",
        entrypoint="scripts.other.convert_x_csv_to_json:main",
    ),
    MenuEntry(
        key="convert_y_csv",
        label="Y CSV 转 YAML",
        entrypoint="scripts.other.convert_y_csv_to_json:main",
    ),
    MenuEntry(
        key="upload_r2",
        label="上传到 R2",
        entrypoint="scripts.r2_upload.upload_images_to_r2:main",
    ),
    MenuEntry(
        key="clear_r2_bucket",
        label="清空 R2 桶",
        entrypoint="scripts.r2_upload.clear_bucket:main",
    ),
    MenuEntry(
        key="delete_run",
        label="删除 Run（数据库 + R2）",
        entrypoint="scripts.r2_upload.delete_run:main",
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
