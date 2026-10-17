#!/usr/bin/env python3
"""删除指定评测的所有数据：Supabase 数据库记录 + R2 存储对象。

基本用法:
  uv run python -m scripts.r2_upload.delete_run --run-dir run-xxx
  uv run python -m scripts.r2_upload.delete_run --run-dir run-xxx --dry-run
  uv run python -m scripts.r2_upload.delete_run --run-dir run-xxx --yes
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from scripts.env_loading import EnvConfigError, argv_requests_local, load_env_files
from scripts.run_naming import validate_run_key

from .postgrest_http import _PostgrestHTTPClient, _PostgrestHTTPError, _to_postgrest_eq_filter
from .supabase_env import MissingRequiredEnvError, require_env


class _ConfigError(Exception):
    pass


def _require_env_safe(name: str) -> str:
    try:
        return require_env(name)
    except MissingRequiredEnvError:
        raw = os.getenv(name)
        if raw and raw.strip():
            return raw.strip()
        raise


def _build_s3_client():
    endpoint = _require_env_safe("R2_ENDPOINT")
    access_key_id = _require_env_safe("R2_ACCESS_KEY_ID")
    secret_access_key = _require_env_safe("R2_SECRET_ACCESS_KEY")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 0}),
    )


def _build_supabase_client() -> _PostgrestHTTPClient:
    return _PostgrestHTTPClient(
        _require_env_safe("SUPABASE_URL"),
        _require_env_safe("SUPABASE_SERVICE_ROLE_KEY"),
    )


def list_db_runs(*, local: bool = False) -> list[str]:
    """查询 Supabase runs 表，返回所有评测的 run_dir 名称列表。"""
    load_env_files(local=local)
    client = _build_supabase_client()
    data = client.request_json(
        method="GET",
        table_name="runs",
        query_params=(("select", "run_dir"), ("order", "run_dir.asc")),
        body=None,
        extra_headers={},
    )
    if not isinstance(data, list):
        return []
    return [
        row["run_dir"]
        for row in data
        if isinstance(row, dict) and isinstance(row.get("run_dir"), str)
    ]


def _get_buckets() -> list[tuple[str, str]]:
    public = _require_env_safe("R2_PUBLIC_BUCKET")
    private = _require_env_safe("R2_PRIVATE_BUCKET")
    if public == private:
        return [(public, "public/private")]
    return [(public, "public"), (private, "private")]


def _delete_r2_objects(
    run_dir: str,
    dry_run: bool,
    *,
    s3_client: Any | None = None,
) -> dict[str, int]:
    s3 = _build_s3_client() if s3_client is None else s3_client
    buckets = _get_buckets()
    prefix = f"runs/{run_dir}/"
    result: dict[str, int] = {}

    for bucket_name, label in buckets:
        deleted = 0
        continuation_token: str | None = None

        while True:
            request: dict[str, object] = {
                "Bucket": bucket_name,
                "Prefix": prefix,
                "MaxKeys": 1000,
            }
            if continuation_token:
                request["ContinuationToken"] = continuation_token

            response = s3.list_objects_v2(**request)
            contents = response.get("Contents", [])
            if not isinstance(contents, list) or not contents:
                break

            objects = []
            for item in contents:
                if isinstance(item, dict):
                    key = item.get("Key")
                    if isinstance(key, str) and key:
                        objects.append({"Key": key})

            if not objects:
                break

            if dry_run:
                deleted += len(objects)
            else:
                delete_resp = s3.delete_objects(
                    Bucket=bucket_name,
                    Delete={"Objects": objects, "Quiet": False},
                )
                deleted_items = delete_resp.get("Deleted", [])
                deleted += (
                    len(deleted_items) if isinstance(deleted_items, list) else len(objects)
                )

            is_truncated = bool(response.get("IsTruncated", False))
            next_token = response.get("NextContinuationToken")
            if is_truncated and isinstance(next_token, str) and next_token:
                continuation_token = next_token
                continue
            break

        if deleted > 0:
            result[label] = deleted

    return result


def _get_db_run_count(
    run_dir: str, *, client: _PostgrestHTTPClient | None = None
) -> int:
    db = _build_supabase_client() if client is None else client
    try:
        data = db.request_json(
            method="GET",
            table_name="runs",
            query_params=(
                ("select", "id"),
                ("run_dir", _to_postgrest_eq_filter(run_dir)),
                ("limit", "1"),
            ),
            body=None,
            extra_headers={},
        )
    except _PostgrestHTTPError:
        return 0
    if isinstance(data, list):
        return len(data)
    return 0


def _delete_supabase_run(
    run_dir: str, *, client: _PostgrestHTTPClient | None = None
) -> int:
    db = _build_supabase_client() if client is None else client
    try:
        data = db.request_json(
            method="DELETE",
            table_name="runs",
            query_params=(("run_dir", _to_postgrest_eq_filter(run_dir)),),
            body=None,
            extra_headers={"Prefer": "return=representation"},
        )
    except _PostgrestHTTPError:
        return 0
    if isinstance(data, list):
        return len(data)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="删除指定 run 的所有数据：Supabase 数据库记录 + R2 存储对象",
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="要删除的 run 目录名（如 run-abc123）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，不实际执行删除",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="跳过交互确认",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help=(
            "只删除本地开发数据库的行（.env.local-db），"
            "绝不删除生产 R2 对象"
        ),
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    s3_client_factory: Callable[[], Any] | None = None,
    supabase_client_factory: Callable[[], _PostgrestHTTPClient] | None = None,
) -> int:
    local = argv_requests_local(argv)
    try:
        load_env_files(local=local)
    except EnvConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2
    except Exception:
        pass

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        run_dir = validate_run_key(args.run_dir, field_name="run-dir")
    except ValueError as exc:
        print(f"参数错误: {exc}", file=sys.stderr)
        return 2

    try:
        _require_env_safe("SUPABASE_URL")
        _require_env_safe("SUPABASE_SERVICE_ROLE_KEY")
        if not local:
            _require_env_safe("R2_ENDPOINT")
    except (MissingRequiredEnvError, _ConfigError) as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    make_s3_client = s3_client_factory or _build_s3_client
    make_supabase_client = supabase_client_factory or _build_supabase_client

    # 预览模式仍显示统计
    try:
        r2_deleted_preview: dict[str, int] = {}
        if not local:
            r2_deleted_preview = _delete_r2_objects(
                run_dir, dry_run=True, s3_client=make_s3_client()
            )
        db_count = _get_db_run_count(run_dir, client=make_supabase_client())
    except ClientError as exc:
        print(f"R2 API 错误: {exc}", file=sys.stderr)
        return 1
    except _PostgrestHTTPError as exc:
        print(f"Supabase 错误: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        return 1

    total_r2_preview = sum(r2_deleted_preview.values())

    if db_count == 0 and (local or total_r2_preview == 0):
        if local:
            print(
                f"未找到 run_dir={run_dir} 的任何数据（本地数据库为空），无需删除。"
            )
        else:
            print(
                f"未找到 run_dir={run_dir} 的任何数据（R2 和数据库均为空），无需删除。"
            )
        return 0

    # 输出统计信息
    print(f"目标 run: {run_dir}")
    if local:
        print("  数据库目标: 本地开发库（--local）")
        print("  R2: 已跳过 R2 对象删除（本地库是生产库镜像，生产对象不受影响）")
    else:
        print(f"  R2 对象 ({' + '.join(r2_deleted_preview.keys()) or '无'}): {total_r2_preview} 个")
    print(f"  数据库记录: {db_count} 条 runs 记录（含所有关联子表数据）")

    if args.dry_run:
        print("dry-run 完成，未执行实际删除。")
        return 0

    if not args.yes:
        try:
            response = input("确认执行删除操作？[y/N] ").strip().lower()
        except EOFError:
            response = "n"
        except KeyboardInterrupt:
            print("\n已取消。")
            return 130
        if response not in {"y", "yes"}:
            print("已取消删除操作。")
            return 0

    try:
        # 1. 删除 R2 对象；本地开发阶段只删镜像库的行，不碰生产对象
        if not local:
            r2_deleted = _delete_r2_objects(
                run_dir, dry_run=False, s3_client=make_s3_client()
            )
            for label, count in r2_deleted.items():
                print(f"  R2 [{label}]: 已删除 {count} 个对象")
            if not r2_deleted:
                print("  R2: 无对象待删除")

        # 2. 删除数据库记录（CASCADE 自动处理子表）
        db_deleted = _delete_supabase_run(run_dir, client=make_supabase_client())
        print(f"  数据库: 已删除 {db_deleted} 条 runs 记录（级联删除所有关联子表数据）")

        return 0
    except ClientError as exc:
        print(f"R2 API 错误: {exc}", file=sys.stderr)
        return 1
    except _PostgrestHTTPError as exc:
        print(f"Supabase 错误: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消。")
        return 130
    except Exception as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
