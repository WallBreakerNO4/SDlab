# pyright: basic, reportUnknownVariableType=false

from __future__ import annotations

import argparse
import os
from collections.abc import MutableMapping
from pathlib import Path

from dotenv import dotenv_values, find_dotenv

DEFAULT_ENV_FILENAME = ".env"
LOCAL_DB_ENV_FILENAME = ".env.local-db"
LOCAL_FLAG = "--local"

# `--local` 只切换数据库目标；local-db 里若混入 R2 变量，既不覆盖也不加载，
# 否则一次手滑就会把资源写到别处。R2 配置始终来自进程 env 或 `.env`。
_LOCAL_DB_ALLOWED_PREFIXES = ("SUPABASE_", "NEXT_PUBLIC_SUPABASE_")


class EnvConfigError(RuntimeError):
    """env 文件缺失或不可用时的配置错误。"""

    category = "config"
    context: dict[str, object]

    def __init__(
        self,
        message: str,
        *,
        code: str = "missing_env_file",
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def argv_requests_local(argv: list[str] | None) -> bool:
    """在正式解析前判定 `--local`，因为 env 文件必须在 build_parser 之前加载。"""
    probe = argparse.ArgumentParser(add_help=False)
    _ = probe.add_argument(LOCAL_FLAG, action="store_true")
    _ = probe.add_argument("-h", "--help", action="store_true")
    try:
        known, _ = probe.parse_known_args(argv)
    except SystemExit:
        return False
    # 帮助信息不该因为缺少 .env.local-db 而打不开。
    if bool(known.help):
        return False
    return bool(known.local)


def load_env_files(
    *,
    local: bool = False,
    env_dir: Path | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """加载 Python 侧 env 文件。

    默认只读 `.env`，与既有脚本行为一致。`local=True` 时先读 `.env.local-db`
    再读 `.env`：前者赢，后者补漏其余机密（R2 凭据等）。
    """
    target = os.environ if environ is None else environ

    if local:
        local_path = _resolve_env_file(LOCAL_DB_ENV_FILENAME, env_dir)
        if local_path is None:
            raise EnvConfigError(
                f"missing {LOCAL_DB_ENV_FILENAME}: --local 需要本地数据库环境文件；"
                "请按 .env.example 说明创建（值从 "
                "`pnpm dlx supabase status -o env` 抄写），不会回退到远端数据库",
                context={"env_file": LOCAL_DB_ENV_FILENAME},
            )
        # --local 是显式的数据库目标声明。覆盖进程里可能残留的远端数据库连接
        # 变量，避免一次误写生产库；local-db 只允许提供数据库键。
        _apply_env_file(
            local_path,
            target,
            override=True,
            allowed_prefixes=_LOCAL_DB_ALLOWED_PREFIXES,
        )

    dotenv_path = _resolve_env_file(DEFAULT_ENV_FILENAME, env_dir)
    if dotenv_path is not None:
        _apply_env_file(dotenv_path, target, override=False)


def _resolve_env_file(filename: str, env_dir: Path | None) -> Path | None:
    if env_dir is not None:
        candidate = env_dir / filename
        return candidate if candidate.is_file() else None
    found = find_dotenv(filename=filename, usecwd=True)
    if not found:
        return None
    return Path(found)


def _apply_env_file(
    path: Path,
    target: MutableMapping[str, str],
    *,
    override: bool,
    allowed_prefixes: tuple[str, ...] | None = None,
) -> None:
    for key, value in dotenv_values(path, encoding="utf-8").items():
        if value is None:
            continue
        if allowed_prefixes is not None and not key.startswith(allowed_prefixes):
            continue
        if override or key not in target:
            target[key] = value
