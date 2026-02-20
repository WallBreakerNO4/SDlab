#!/usr/bin/env python3
"""程序入口点：ComfyUI 网格生图工具"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
ROOT = Path(__file__).resolve().parents[0]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generation.comfyui_part1_generate import main as generate_main


def main(argv: list[str] | None = None) -> int:
    """主入口点，委托给 scripts.generation.comfyui_part1_generate.main()"""
    return generate_main(argv)


if __name__ == "__main__":
    sys.exit(main())
