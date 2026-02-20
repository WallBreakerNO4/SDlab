from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    from .upload_images_to_r2 import main as _main

    return _main(argv)


__all__ = ["main"]
