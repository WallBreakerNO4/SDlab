from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload ComfyUI images to R2 (skeleton, not implemented)."
    )
    _ = parser.add_argument(
        "--run-root",
        default="comfyui_api_outputs",
        help="Root directory containing run-* folders.",
    )
    _ = parser.add_argument("--run-dir", help="Specific run directory name.")
    _ = parser.add_argument(
        "--all-runs",
        action="store_true",
        help="Process all runs under --run-root.",
    )
    _ = parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without network or database writes.",
    )
    _ = parser.add_argument(
        "--category",
        choices=["normal", "advance", "nsfw"],
        help="Optional category override.",
    )
    _ = parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Reserved concurrency option.",
    )
    _ = parser.add_argument(
        "--limit",
        type=int,
        help="Reserved limit for number of images.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 1

    dry_run = bool(getattr(args, "dry_run", False))
    mode = "dry-run" if dry_run else "execution"
    print(f"R2 uploader skeleton only: {mode} is not implemented yet.")
    print("Accepted arguments are parsed and currently ignored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
