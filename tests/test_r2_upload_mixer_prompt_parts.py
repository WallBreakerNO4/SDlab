from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.r2_upload.upload_planner import _enrich_legacy_mixer_prompt_parts


def _write_y_prompt(path: Path) -> str:
    path.write_text(
        """
schema: prompt-y-table/v3
collection_id: mixer-styles
items:
  - tags:
      - text: artist-a
        weight: 1.1
        type: artists
      - text: no lineart
        weight: 1.0
        type: general
    info:
      index: 2
""".lstrip(),
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_json(y_path: Path, y_sha256: str) -> dict[str, object]:
    return {
        "model": {"artist_weight_profile": "identity"},
        "config_snapshot": {
            "prompts": {
                "y_path": str(y_path),
                "y_sha256": y_sha256,
            },
            "workflow": {"anima_artist_mixer": True},
        },
    }


def test_legacy_mixer_prompt_parts_are_backfilled_from_verified_y_asset(
    tmp_path: Path,
) -> None:
    y_path = tmp_path / "styles.yaml"
    y_sha256 = _write_y_prompt(y_path)
    records = [
        {
            "status": "success",
            "x_index": 0,
            "y_index": 0,
            "artist_chain": "1.1::@artist-a",
            "y_style_key": "mixer-styles:2",
            "y_collection_id": "mixer-styles",
            "y_item_index": 2,
        }
    ]

    enriched = _enrich_legacy_mixer_prompt_parts(
        run_json=_run_json(y_path, y_sha256),
        metadata_records=records,
    )

    assert enriched[0]["artist_chain"] == "1.1::@artist-a"
    assert enriched[0]["y_common_prompt"] == "no lineart, "
    assert "y_common_prompt" not in records[0]


def test_legacy_mixer_backfill_rejects_changed_y_asset(tmp_path: Path) -> None:
    y_path = tmp_path / "styles.yaml"
    _ = _write_y_prompt(y_path)
    records = [
        {
            "status": "success",
            "y_style_key": "mixer-styles:2",
        }
    ]

    with pytest.raises(ValueError, match="SHA256 不一致"):
        _enrich_legacy_mixer_prompt_parts(
            run_json=_run_json(y_path, "0" * 64),
            metadata_records=records,
        )


def test_new_mixer_metadata_does_not_reopen_y_asset(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.yaml"
    records = [
        {
            "status": "success",
            "artist_chain": "@artist-a",
            "y_common_prompt": "",
        }
    ]

    enriched = _enrich_legacy_mixer_prompt_parts(
        run_json=_run_json(missing_path, "0" * 64),
        metadata_records=records,
    )

    assert enriched is records
