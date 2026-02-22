#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import find_dotenv, load_dotenv


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
            Delete={"Objects": objects, "Quiet": True},
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


def main() -> int:
    try:
        _autoload_dotenv()
        bucket_name = input("请输入要清空的 R2 桶名: ").strip()
        if not bucket_name:
            print("错误: 桶名不能为空")
            return 2

        deleted_total = _clear_bucket(bucket_name)
        print(f"完成: 已清空桶 {bucket_name}，删除对象数 {deleted_total}")
        return 0
    except ClientError as exc:
        print(f"R2 API 错误: {exc}")
        return 1
    except Exception as exc:
        print(f"执行失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
