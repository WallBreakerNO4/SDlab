from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="R2 上传脚本（未实现）")


def main(argv: list[str] | None = None) -> int:
    _ = build_parser().parse_args(argv)
    raise NotImplementedError("R2 上传脚本尚未实现")


if __name__ == "__main__":
    raise SystemExit(main())
