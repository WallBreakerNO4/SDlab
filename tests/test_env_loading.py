# pyright: basic, reportMissingImports=false

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.env_loading import EnvConfigError, load_env_files


def _write_env_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_local_mode_prefers_local_db_and_fills_gaps_from_env(
    tmp_path: Path,
) -> None:
    _write_env_file(
        tmp_path / ".env.local-db",
        "SUPABASE_URL=http://127.0.0.1:54321\n"
        "SUPABASE_SERVICE_ROLE_KEY=local-service-key\n",
    )
    _write_env_file(
        tmp_path / ".env",
        "SUPABASE_URL=https://prod.example.supabase.co\n"
        "SUPABASE_SERVICE_ROLE_KEY=prod-service-key\n"
        "R2_PUBLIC_BUCKET=prod-public-bucket\n",
    )
    environ: dict[str, str] = {}

    load_env_files(local=True, env_dir=tmp_path, environ=environ)

    assert environ["SUPABASE_URL"] == "http://127.0.0.1:54321"
    assert environ["SUPABASE_SERVICE_ROLE_KEY"] == "local-service-key"
    assert environ["R2_PUBLIC_BUCKET"] == "prod-public-bucket"


def test_local_mode_overrides_stale_process_database_target(
    tmp_path: Path,
) -> None:
    _write_env_file(
        tmp_path / ".env.local-db",
        "SUPABASE_URL=http://127.0.0.1:54321\n",
    )
    _write_env_file(
        tmp_path / ".env",
        "SUPABASE_URL=https://prod.example.supabase.co\n",
    )
    environ = {"SUPABASE_URL": "https://stale.example.supabase.co"}

    load_env_files(local=True, env_dir=tmp_path, environ=environ)

    assert environ["SUPABASE_URL"] == "http://127.0.0.1:54321"


def test_default_mode_ignores_local_db_file(tmp_path: Path) -> None:
    _write_env_file(
        tmp_path / ".env.local-db",
        "SUPABASE_URL=http://127.0.0.1:54321\n",
    )
    _write_env_file(
        tmp_path / ".env",
        "SUPABASE_URL=https://prod.example.supabase.co\n",
    )
    environ: dict[str, str] = {}

    load_env_files(env_dir=tmp_path, environ=environ)

    assert environ == {"SUPABASE_URL": "https://prod.example.supabase.co"}


def test_default_mode_keeps_existing_process_values(tmp_path: Path) -> None:
    _write_env_file(
        tmp_path / ".env",
        "SUPABASE_URL=https://prod.example.supabase.co\n"
        "R2_PUBLIC_BUCKET=prod-public-bucket\n",
    )
    environ = {"SUPABASE_URL": "https://shell.example.supabase.co"}

    load_env_files(env_dir=tmp_path, environ=environ)

    assert environ["SUPABASE_URL"] == "https://shell.example.supabase.co"
    assert environ["R2_PUBLIC_BUCKET"] == "prod-public-bucket"


def test_local_mode_ignores_non_database_keys_from_local_db(
    tmp_path: Path,
) -> None:
    _write_env_file(
        tmp_path / ".env.local-db",
        "SUPABASE_URL=http://127.0.0.1:54321\n"
        "R2_PUBLIC_BUCKET=accidental-local-bucket\n",
    )
    _write_env_file(
        tmp_path / ".env",
        "R2_PUBLIC_BUCKET=prod-public-bucket\n",
    )
    environ: dict[str, str] = {}

    load_env_files(local=True, env_dir=tmp_path, environ=environ)

    assert environ["SUPABASE_URL"] == "http://127.0.0.1:54321"
    assert environ["R2_PUBLIC_BUCKET"] == "prod-public-bucket"


def test_local_mode_without_local_db_file_raises_config_error(
    tmp_path: Path,
) -> None:
    _write_env_file(
        tmp_path / ".env",
        "SUPABASE_URL=https://prod.example.supabase.co\n",
    )

    with pytest.raises(EnvConfigError) as excinfo:
        load_env_files(local=True, env_dir=tmp_path, environ={})

    assert ".env.local-db" in str(excinfo.value)
    assert excinfo.value.category == "config"
    assert excinfo.value.context["env_file"] == ".env.local-db"
