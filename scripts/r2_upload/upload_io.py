# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _to_json_line(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def _load_run_json(run_dir: Path) -> dict[str, object]:
    run_json_path = run_dir / "run.json"
    raw = run_json_path.read_text(encoding="utf-8")
    parsed = cast(object, json.loads(raw))
    if not isinstance(parsed, dict):
        raise ValueError(f"run.json 必须是对象: {run_json_path}")
    return cast(dict[str, object], parsed)


def _load_metadata_records(run_dir: Path) -> list[dict[str, object]]:
    metadata_path = run_dir / "metadata.jsonl"
    rows: list[dict[str, object]] = []
    for line_number, raw_line in enumerate(
        metadata_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = raw_line.strip()
        if not stripped:
            continue
        parsed = cast(object, json.loads(stripped))
        if not isinstance(parsed, dict):
            raise ValueError(
                f"metadata.jsonl 第 {line_number} 行必须是对象: {metadata_path}"
            )
        rows.append(cast(dict[str, object], parsed))
    return rows


def _variant_extension(variant: str) -> str:
    if variant == "display_webp" or variant == "thumb_webp":
        return ".webp"
    if variant == "display_avif" or variant == "thumb_avif":
        return ".avif"
    return ".bin"


def _write_intermediate_variant(
    *,
    run_intermediate_dir: Path,
    original_sha256: str,
    batch_index: int,
    variant: str,
    body_bytes: bytes,
) -> tuple[Path, str]:
    safe_variant = variant.replace("/", "_")
    output_name = f"{original_sha256}-{batch_index:06d}-{safe_variant}{_variant_extension(variant)}"
    output_path = run_intermediate_dir / output_name
    if output_path.exists():
        cached_sha256 = _sha256_file(output_path)
        return output_path, cached_sha256

    output_path.write_bytes(body_bytes)
    written_sha256 = _sha256_hex(body_bytes)
    return output_path, written_sha256


def _intermediate_variant_path(
    *,
    run_intermediate_dir: Path,
    original_sha256: str,
    batch_index: int,
    variant: str,
) -> Path:
    safe_variant = variant.replace("/", "_")
    output_name = f"{original_sha256}-{batch_index:06d}-{safe_variant}{_variant_extension(variant)}"
    return run_intermediate_dir / output_name
