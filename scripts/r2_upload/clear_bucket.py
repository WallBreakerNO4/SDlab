#!/usr/bin/env python3
from __future__ import annotations

import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import find_dotenv, load_dotenv


CLEAR_TARGET_ENV = "SDSLAB_R2_CLEAR_BUCKET_TARGET"
LEGACY_CLEAR_BUCKET_ENV = "SDSLAB_R2_CLEAR_BUCKET_NAME"


def _autoload_dotenv() -> None:
    dotenv_path = find_dotenv(filename=".env", usecwd=True)
    if dotenv_path:
        _ = load_dotenv(dotenv_path=dotenv_path, encoding="utf-8")


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"missing required env: {name}")
    return value.strip()


def _build_s3_client():
    endpoint = _require_env("R2_ENDPOINT")
    access_key_id = _require_env("R2_ACCESS_KEY_ID")
    secret_access_key = _require_env("R2_SECRET_ACCESS_KEY")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 0}),
    )


def _require_bucket_names() -> dict[str, str]:
    return {
        "public": _require_env("R2_PUBLIC_BUCKET"),
        "private": _require_env("R2_PRIVATE_BUCKET"),
    }


def _resolve_selected_buckets(
    raw_target: str, bucket_names: dict[str, str]
) -> tuple[str, ...] | None:
    normalized = raw_target.strip().lower()
    if not normalized:
        return None

    public_bucket = bucket_names["public"]
    private_bucket = bucket_names["private"]
    if normalized in {"1", "public", "r2_public_bucket", public_bucket.lower()}:
        return (public_bucket,)
    if normalized in {"2", "private", "r2_private_bucket", private_bucket.lower()}:
        return (private_bucket,)
    if normalized in {
        "3",
        "both",
        "all",
        "r2_public_bucket+r2_private_bucket",
        "r2_buckets",
    }:
        if public_bucket == private_bucket:
            return (public_bucket,)
        return (public_bucket, private_bucket)
    if normalized in {
        "4",
        "back",
        "return",
        "cancel",
        "exit",
        "quit",
        "__back__",
        "__exit__",
    }:
        return ()
    return None


def _prompt_clear_target(bucket_names: dict[str, str]) -> str:
    print("请选择要清空的 R2 桶:")
    print(f"1) 清空 R2_PUBLIC_BUCKET ({bucket_names['public']})")
    print(f"2) 清空 R2_PRIVATE_BUCKET ({bucket_names['private']})")
    print("3) 清空二者")
    print("4) 返回")
    return input("请输入选项 [1-4]: ").strip()


def _clear_bucket(bucket_name: str) -> int:
    s3 = _build_s3_client()
    continuation_token: str | None = None
    deleted_total = 0

    while True:
        request: dict[str, object] = {"Bucket": bucket_name, "MaxKeys": 1000}
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

        delete_resp = s3.delete_objects(
            Bucket=bucket_name,
            Delete={"Objects": objects, "Quiet": False},
        )

        deleted_items = delete_resp.get("Deleted", [])
        if isinstance(deleted_items, list):
            deleted_total += len(deleted_items)
        else:
            deleted_total += len(objects)

        is_truncated = bool(response.get("IsTruncated", False))
        next_token = response.get("NextContinuationToken")
        if is_truncated and isinstance(next_token, str) and next_token:
            continuation_token = next_token
            continue
        break

    return deleted_total


def main(argv: list[str] | None = None) -> int:
    _ = argv
    try:
        _autoload_dotenv()
        bucket_names = _require_bucket_names()
        selected_buckets = _resolve_selected_buckets(
            os.getenv(CLEAR_TARGET_ENV) or os.getenv(LEGACY_CLEAR_BUCKET_ENV) or "",
            bucket_names,
        )
        if selected_buckets is None:
            selected_buckets = _resolve_selected_buckets(
                _prompt_clear_target(bucket_names),
                bucket_names,
            )
        if selected_buckets is None:
            print(
                "错误: 无效选项，请选择 R2_PUBLIC_BUCKET、R2_PRIVATE_BUCKET、二者或返回"
            )
            return 2
        if not selected_buckets:
            print("已取消清空 R2 桶。")
            return 0

        deleted_total = 0
        for bucket_name in selected_buckets:
            bucket_deleted_total = _clear_bucket(bucket_name)
            deleted_total += bucket_deleted_total
            print(f"完成: 已清空桶 {bucket_name}，删除对象数 {bucket_deleted_total}")
        if len(selected_buckets) > 1:
            print(
                f"汇总: 已清空 {len(selected_buckets)} 个桶，总删除对象数 {deleted_total}"
            )
        return 0
    except KeyboardInterrupt:
        print("已取消清空 R2 桶。")
        return 130
    except ClientError as exc:
        print(f"R2 API 错误: {exc}")
        return 1
    except Exception as exc:
        print(f"执行失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
