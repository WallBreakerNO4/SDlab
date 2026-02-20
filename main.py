#!/usr/bin/env python3
"""程序入口点：ComfyUI 网格生图工具"""

import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# 添加项目根目录到 Python 路径
ROOT = Path(__file__).resolve().parents[0]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generation.comfyui_part1_generate import main as generate_main
from scripts.cli.io import MenuIO
from scripts.cli.menu import run_menu

MENU_FLAG = "--menu"


def _effective_argv(argv: list[str] | None) -> list[str]:
    if argv is None:
        return list(sys.argv[1:])
    return list(argv)


def main(argv: list[str] | None = None) -> int:
    _autoload_dotenv()
    effective_argv = _effective_argv(argv)
    io = MenuIO()
    force_menu = MENU_FLAG in effective_argv

    if force_menu:
        if not io.is_interactive():
            io.write("Error: --menu requires an interactive TTY (stdin/stdout).")
            return 2

        extra_args = [item for item in effective_argv if item != MENU_FLAG]
        if extra_args:
            io.write("Notice: extra args are ignored in menu mode.")
        return run_menu(io)

    if not effective_argv and io.is_interactive():
        return run_menu(io)

    return generate_main(argv)


def _autoload_dotenv() -> None:
    dotenv_path = find_dotenv(filename=".env", usecwd=True)
    if dotenv_path:
        _ = load_dotenv(dotenv_path=dotenv_path, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
