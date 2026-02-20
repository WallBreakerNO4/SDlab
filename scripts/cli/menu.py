from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import shlex

from .io import MenuIO
from .registry import MenuEntry, iter_entries, load_entrypoint

QUIT_TOKENS = frozenset({"q", "quit", "exit"})
GENERATE_ENTRY_KEY = "generate_grid"
GENERATE_BASE_COMMAND = "uv run python scripts/generation/comfyui_part1_generate.py"
CONVERT_X_BASE_COMMAND = "uv run python scripts/other/convert_x_csv_to_json.py"
CONVERT_Y_BASE_COMMAND = "uv run python scripts/other/convert_y_csv_to_json.py"
UPLOAD_R2_BASE_COMMAND = "uv run python scripts/r2_upload/upload_images_to_r2.py"


@dataclass(frozen=True, slots=True)
class MenuSelection:
    raw: str
    entry: MenuEntry | None
    should_exit: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ReadResult:
    value: str | None = None
    exit_code: int | None = None


def _default_entries() -> tuple[MenuEntry, ...]:
    return tuple(iter_entries(include_disabled=True))


def build_menu_lines(entries: Sequence[MenuEntry] | None = None) -> tuple[str, ...]:
    menu_entries = tuple(entries) if entries is not None else _default_entries()
    lines = ["Available scripts:"]
    for index, entry in enumerate(menu_entries, start=1):
        suffix = "" if entry.enabled else " (disabled)"
        lines.append(f"{index}. {entry.label} [{entry.key}]{suffix}")
    lines.append("q. Quit")
    return tuple(lines)


def select_entry(
    raw_choice: str,
    entries: Sequence[MenuEntry] | None = None,
) -> MenuSelection:
    menu_entries = tuple(entries) if entries is not None else _default_entries()
    choice = raw_choice.strip()

    if not choice:
        return MenuSelection(
            raw=choice, entry=None, should_exit=False, error="Empty choice"
        )

    lowered = choice.lower()
    if lowered in QUIT_TOKENS:
        return MenuSelection(raw=choice, entry=None, should_exit=True)

    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(menu_entries):
            entry = menu_entries[index]
        else:
            return MenuSelection(
                raw=choice,
                entry=None,
                should_exit=False,
                error="Choice out of range",
            )
    else:
        matched = next((item for item in menu_entries if item.key == choice), None)
        if matched is None:
            return MenuSelection(
                raw=choice,
                entry=None,
                should_exit=False,
                error="Unknown choice",
            )
        entry = matched

    if not entry.enabled:
        return MenuSelection(
            raw=choice,
            entry=entry,
            should_exit=False,
            error="Entry disabled",
        )

    return MenuSelection(raw=choice, entry=entry, should_exit=False)


def prompt_once(
    io: MenuIO,
    entries: Sequence[MenuEntry] | None = None,
    *,
    prompt: str = "Select an option: ",
) -> MenuSelection:
    menu_entries = tuple(entries) if entries is not None else _default_entries()
    for line in build_menu_lines(menu_entries):
        io.write(line)
    raw_choice = io.read(prompt)
    return select_entry(raw_choice, menu_entries)


def run_menu(
    io: MenuIO,
    entries: Sequence[MenuEntry] | None = None,
    *,
    prompt: str = "Select an option: ",
    invalid_prefix: str = "Invalid selection: ",
    placeholder_message: str = "该选项即将支持，后续实现。",
) -> int:
    menu_entries = tuple(entries) if entries is not None else _default_entries()

    io.write("")
    io.write("提示：无参+TTY 自动进入菜单；带参时透传到生图脚本。")
    io.write("提示：使用 --menu 强制进入菜单；非 TTY 会拒绝并提示。")
    io.write("提示：选择脚本后会打印可复制命令模板，并二次确认。")
    io.write("")

    while True:
        for line in build_menu_lines(menu_entries):
            io.write(line)

        choice_result = _safe_read(io, prompt)
        if choice_result.exit_code is not None:
            return choice_result.exit_code
        raw_choice = choice_result.value or ""

        selection = select_entry(raw_choice, menu_entries)
        if selection.should_exit:
            return 0
        if selection.error is not None:
            io.write(f"{invalid_prefix}{selection.error}")
            continue

        if selection.entry is not None and selection.entry.key == GENERATE_ENTRY_KEY:
            extra_argv_result = _safe_read(io, "Extra argv (optional): ")
            if extra_argv_result.exit_code is not None:
                return extra_argv_result.exit_code
            extra_argv_line = (extra_argv_result.value or "").strip()
            try:
                extra_argv = shlex.split(extra_argv_line)
            except ValueError as exc:
                io.write(f"{invalid_prefix}Invalid extra argv: {exc}")
                continue

            preview_command = _build_generate_preview_command(extra_argv)
            io.write(f"Preview command: {preview_command}")

            confirm_result = _safe_read(io, "Confirm execution? [Y/n]: ")
            if confirm_result.exit_code is not None:
                return confirm_result.exit_code
            confirm = (confirm_result.value or "").strip().lower()
            if confirm in {"", "y", "yes"}:
                _run_selection_with_guard(
                    io,
                    selection,
                    extra_argv,
                    success_prefix="Generation finished with exit code: ",
                )
                continue
            else:
                if confirm not in {"n", "no"}:
                    io.write("Invalid confirmation, cancelled.")
                else:
                    io.write("Generation cancelled.")
                continue

        if selection.entry is not None and selection.entry.key == "convert_x_csv":
            extra_argv_result = _safe_read(io, "Extra argv (optional): ")
            if extra_argv_result.exit_code is not None:
                return extra_argv_result.exit_code
            extra_argv_line = (extra_argv_result.value or "").strip()
            try:
                extra_argv = shlex.split(extra_argv_line)
            except ValueError as exc:
                io.write(f"{invalid_prefix}Invalid extra argv: {exc}")
                continue

            preview_command = _build_convert_x_preview_command(extra_argv)
            io.write(f"Preview command: {preview_command}")

            confirm_result = _safe_read(io, "Confirm execution? [Y/n]: ")
            if confirm_result.exit_code is not None:
                return confirm_result.exit_code
            confirm = (confirm_result.value or "").strip().lower()
            if confirm in {"", "y", "yes"}:
                _run_selection_with_guard(
                    io,
                    selection,
                    extra_argv,
                    success_prefix="Convert finished with exit code: ",
                )
                continue
            else:
                if confirm not in {"n", "no"}:
                    io.write("Invalid confirmation, cancelled.")
                else:
                    io.write("Convert cancelled.")
                continue

        if selection.entry is not None and selection.entry.key == "convert_y_csv":
            extra_argv_result = _safe_read(io, "Extra argv (optional): ")
            if extra_argv_result.exit_code is not None:
                return extra_argv_result.exit_code
            extra_argv_line = (extra_argv_result.value or "").strip()
            try:
                extra_argv = shlex.split(extra_argv_line)
            except ValueError as exc:
                io.write(f"{invalid_prefix}Invalid extra argv: {exc}")
                continue

            preview_command = _build_convert_y_preview_command(extra_argv)
            io.write(f"Preview command: {preview_command}")

            confirm_result = _safe_read(io, "Confirm execution? [Y/n]: ")
            if confirm_result.exit_code is not None:
                return confirm_result.exit_code
            confirm = (confirm_result.value or "").strip().lower()
            if confirm in {"", "y", "yes"}:
                _run_selection_with_guard(
                    io,
                    selection,
                    extra_argv,
                    success_prefix="Convert finished with exit code: ",
                )
                continue
            else:
                if confirm not in {"n", "no"}:
                    io.write("Invalid confirmation, cancelled.")
                else:
                    io.write("Convert cancelled.")
                continue

        if selection.entry is not None and selection.entry.key == "upload_r2":
            preview_command = UPLOAD_R2_BASE_COMMAND
            io.write(f"Preview command: {preview_command}")
            io.write("未实现")
            continue

        io.write(placeholder_message)
        return 0


def _build_generate_preview_command(extra_argv: list[str]) -> str:
    if not extra_argv:
        return GENERATE_BASE_COMMAND
    return f"{GENERATE_BASE_COMMAND} {shlex.join(extra_argv)}"


def _build_convert_x_preview_command(extra_argv: list[str]) -> str:
    if not extra_argv:
        return CONVERT_X_BASE_COMMAND
    return f"{CONVERT_X_BASE_COMMAND} {shlex.join(extra_argv)}"


def _build_convert_y_preview_command(extra_argv: list[str]) -> str:
    if not extra_argv:
        return CONVERT_Y_BASE_COMMAND
    return f"{CONVERT_Y_BASE_COMMAND} {shlex.join(extra_argv)}"


def _safe_read(io: MenuIO, prompt: str) -> ReadResult:
    try:
        return ReadResult(value=io.read(prompt))
    except EOFError:
        return ReadResult(exit_code=0)
    except KeyboardInterrupt:
        return ReadResult(exit_code=130)


def _coerce_system_exit_code(code: object) -> int:
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    if isinstance(code, (str, bytes, bytearray)):
        try:
            return int(code)
        except ValueError:
            return 1
    return 1


def _run_selection_with_guard(
    io: MenuIO,
    selection: MenuSelection,
    argv: list[str],
    *,
    success_prefix: str,
) -> None:
    try:
        exit_code = run_selection(selection, argv)
    except SystemExit as exc:
        exit_code = _coerce_system_exit_code(exc.code)
        io.write(f"Script exited with exit code: {exit_code}")
        return
    except Exception as exc:  # noqa: BLE001
        io.write(f"Script execution failed: {exc}")
        return
    io.write(f"{success_prefix}{exit_code}")


def run_selection(selection: MenuSelection, argv: list[str] | None = None) -> int:
    if selection.entry is None:
        raise ValueError("No entry selected")
    if selection.error is not None:
        raise ValueError(selection.error)
    main_func = load_entrypoint(selection.entry)
    return main_func(argv)
