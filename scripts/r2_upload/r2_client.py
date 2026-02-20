# pyright: basic, reportMissingImports=false, reportMissingTypeStubs=false

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Protocol, TypeVar, cast

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    ConnectionClosedError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from scripts.r2_upload.r2_keys import cache_control_for, content_type_for

_MISSING_ENV_MESSAGE = "missing required R2 configuration"
_AUTH_ERROR_CODES = {
    "AccessDenied",
    "InvalidAccessKeyId",
    "SignatureDoesNotMatch",
    "ExpiredToken",
    "TokenRefreshRequired",
}
_THROTTLE_ERROR_CODES = {
    "SlowDown",
    "Throttling",
    "ThrottlingException",
    "TooManyRequestsException",
    "RequestLimitExceeded",
}
_RETRYABLE_ERROR_CODES = _THROTTLE_ERROR_CODES | {
    "InternalError",
    "RequestTimeout",
    "RequestTimeoutException",
    "ServiceUnavailable",
}
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

_T = TypeVar("_T")
BucketScope = Literal["public", "private"]


class S3ClientLike(Protocol):
    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]: ...

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
        CacheControl: str,
    ) -> dict[str, object]: ...


class R2ClientError(RuntimeError):
    category: str
    code: str
    context: dict[str, object]
    retryable: bool

    def __init__(
        self,
        message: str,
        *,
        category: str,
        code: str,
        context: dict[str, object] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.code = code
        self.context = dict(context or {})
        self.retryable = retryable


class R2ConfigError(R2ClientError):
    def __init__(
        self, message: str, *, code: str, context: dict[str, object] | None = None
    ):
        super().__init__(
            message,
            category="config",
            code=code,
            context=context,
            retryable=False,
        )


class R2ArgumentError(R2ClientError):
    def __init__(
        self, message: str, *, code: str, context: dict[str, object] | None = None
    ):
        super().__init__(
            message,
            category="argument",
            code=code,
            context=context,
            retryable=False,
        )


class R2AuthError(R2ClientError):
    def __init__(
        self, message: str, *, code: str, context: dict[str, object] | None = None
    ):
        super().__init__(
            message,
            category="auth",
            code=code,
            context=context,
            retryable=False,
        )


class R2NetworkError(R2ClientError):
    def __init__(
        self, message: str, *, code: str, context: dict[str, object] | None = None
    ):
        super().__init__(
            message,
            category="network",
            code=code,
            context=context,
            retryable=True,
        )


class R2RateLimitError(R2ClientError):
    def __init__(
        self, message: str, *, code: str, context: dict[str, object] | None = None
    ):
        super().__init__(
            message,
            category="rate_limit",
            code=code,
            context=context,
            retryable=True,
        )


class R2RemoteError(R2ClientError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        context: dict[str, object] | None = None,
        retryable: bool = False,
    ):
        super().__init__(
            message,
            category="remote",
            code=code,
            context=context,
            retryable=retryable,
        )


class R2RetryExhaustedError(R2ClientError):
    def __init__(
        self, message: str, *, code: str, context: dict[str, object] | None = None
    ):
        super().__init__(
            message,
            category="retry_exhausted",
            code=code,
            context=context,
            retryable=False,
        )


@dataclass(frozen=True)
class UploadPlan:
    bucket_name: str
    bucket_scope: BucketScope
    key: str
    content_type: str
    cache_control: str
    body_bytes: bytes | None = None
    local_path: str | Path | None = None

    @classmethod
    def from_variant(
        cls,
        *,
        bucket_name: str,
        bucket_scope: BucketScope,
        key: str,
        variant: str,
        body_bytes: bytes | None = None,
        local_path: str | Path | None = None,
    ) -> "UploadPlan":
        return cls(
            bucket_name=bucket_name,
            bucket_scope=bucket_scope,
            key=key,
            content_type=content_type_for(variant),
            cache_control=cache_control_for(bucket_scope),
            body_bytes=body_bytes,
            local_path=local_path,
        )


class _ObjectMissing(Exception):
    pass


class R2Client:
    def __init__(
        self,
        *,
        s3_client: S3ClientLike | None,
        dry_run: bool,
        max_retries: int = 2,
        retry_base_delay_s: float = 0.15,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_retries < 0:
            raise R2ArgumentError(
                "max_retries must be >= 0",
                code="invalid_max_retries",
                context={"max_retries": max_retries},
            )
        if retry_base_delay_s < 0:
            raise R2ArgumentError(
                "retry_base_delay_s must be >= 0",
                code="invalid_retry_delay",
                context={"retry_base_delay_s": retry_base_delay_s},
            )

        self._s3_client: S3ClientLike | None = s3_client
        self.dry_run: bool = dry_run
        self.max_retries: int = max_retries
        self.retry_base_delay_s: float = retry_base_delay_s
        self._sleep: Callable[[float], None] = sleep_fn

    @classmethod
    def from_env(
        cls,
        dry_run: bool,
        *,
        max_retries: int = 2,
        retry_base_delay_s: float = 0.15,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> "R2Client":
        if dry_run:
            return cls(
                s3_client=None,
                dry_run=True,
                max_retries=max_retries,
                retry_base_delay_s=retry_base_delay_s,
                sleep_fn=sleep_fn,
            )

        endpoint = _require_env("R2_ENDPOINT")
        access_key_id = _require_env("R2_ACCESS_KEY_ID")
        secret_access_key = _require_env("R2_SECRET_ACCESS_KEY")

        client = cast(
            S3ClientLike,
            boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name="auto",
                config=Config(signature_version="s3v4", retries={"max_attempts": 0}),
            ),
        )
        return cls(
            s3_client=client,
            dry_run=False,
            max_retries=max_retries,
            retry_base_delay_s=retry_base_delay_s,
            sleep_fn=sleep_fn,
        )

    def head_exists(
        self,
        bucket_name: str,
        key: str,
        *,
        bucket_scope: BucketScope = "private",
    ) -> bool:
        _validate_bucket_scope(bucket_scope)
        _validate_bucket_name_and_key(bucket_name, key)
        if self.dry_run:
            return False

        client = self._require_client()
        object_ref = _safe_object_ref(bucket_scope, key)

        def _invoke() -> dict[str, object]:
            try:
                return client.head_object(Bucket=bucket_name, Key=key)
            except ClientError as exc:
                if _is_not_found(exc):
                    raise _ObjectMissing() from exc
                raise

        try:
            _ = self._run_with_retry("head_object", object_ref, _invoke)
            return True
        except _ObjectMissing:
            return False

    def put_bytes(self, plan: UploadPlan) -> None:
        _validate_bucket_scope(plan.bucket_scope)
        _validate_bucket_name_and_key(plan.bucket_name, plan.key)
        _validate_headers(plan.content_type, plan.cache_control)
        body = _resolve_upload_body(plan)
        if self.dry_run:
            return

        client = self._require_client()
        object_ref = _safe_object_ref(plan.bucket_scope, plan.key)

        def _invoke() -> dict[str, object]:
            return client.put_object(
                Bucket=plan.bucket_name,
                Key=plan.key,
                Body=body,
                ContentType=plan.content_type,
                CacheControl=plan.cache_control,
            )

        _ = self._run_with_retry("put_object", object_ref, _invoke)

    def upload(self, plan: UploadPlan) -> None:
        self.put_bytes(plan)

    def _run_with_retry(
        self,
        op: str,
        object_ref: dict[str, object],
        fn: Callable[[], _T],
    ) -> _T:
        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                return fn()
            except _ObjectMissing:
                raise
            except Exception as exc:
                mapped = self._map_exception(exc, op=op, object_ref=object_ref)
                if mapped.retryable and attempt < attempts:
                    self._sleep(self.retry_base_delay_s * (2 ** (attempt - 1)))
                    continue
                if mapped.retryable:
                    raise R2RetryExhaustedError(
                        "r2 operation retry exhausted",
                        code="retry_exhausted",
                        context={
                            "operation": op,
                            "attempts": attempts,
                            "last_error_code": mapped.code,
                            **object_ref,
                        },
                    ) from exc
                raise mapped from exc

        raise R2RetryExhaustedError(
            "r2 operation retry exhausted",
            code="retry_exhausted",
            context={"operation": op, "attempts": attempts, **object_ref},
        )

    def _map_exception(
        self,
        exc: Exception,
        *,
        op: str,
        object_ref: dict[str, object],
    ) -> R2ClientError:
        context = {"operation": op, **object_ref}

        if isinstance(
            exc,
            (
                EndpointConnectionError,
                ConnectTimeoutError,
                ReadTimeoutError,
                ConnectionClosedError,
            ),
        ):
            return R2NetworkError(
                "r2 network request failed",
                code="network_error",
                context=context,
            )

        if isinstance(exc, ClientError):
            response = cast(dict[str, object], exc.response)
            error_obj = response.get("Error", {})
            if not isinstance(error_obj, dict):
                error_obj = {}
            error_code = str(error_obj.get("Code", "unknown"))

            metadata_obj = response.get("ResponseMetadata", {})
            status_code = 0
            if isinstance(metadata_obj, dict):
                raw_status = metadata_obj.get("HTTPStatusCode")
                if isinstance(raw_status, int):
                    status_code = raw_status

            context = {
                **context,
                "remote_error_code": error_code,
                "remote_status": status_code,
            }

            if error_code in _AUTH_ERROR_CODES or status_code in {401, 403}:
                return R2AuthError(
                    "r2 authentication failed",
                    code="auth_error",
                    context=context,
                )

            if error_code in _THROTTLE_ERROR_CODES or status_code == 429:
                return R2RateLimitError(
                    "r2 request was rate limited",
                    code="rate_limited",
                    context=context,
                )

            retryable_remote = (
                error_code in _RETRYABLE_ERROR_CODES
                or status_code in _RETRYABLE_STATUS_CODES
            )
            return R2RemoteError(
                "r2 remote service returned an error",
                code="remote_error",
                context=context,
                retryable=retryable_remote,
            )

        return R2RemoteError(
            "r2 operation failed with unexpected error",
            code="unexpected_error",
            context=context,
            retryable=False,
        )

    def _require_client(self) -> S3ClientLike:
        if self._s3_client is None:
            raise R2ConfigError(
                "r2 client is not initialized",
                code="missing_client",
            )
        return self._s3_client


def _safe_object_ref(bucket_scope: BucketScope, key: str) -> dict[str, object]:
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return {
        "bucket_scope": bucket_scope,
        "key_hash12": key_hash,
        "key_len": len(key),
    }


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise R2ConfigError(
            _MISSING_ENV_MESSAGE,
            code="missing_env",
            context={"missing_env": name},
        )
    return value.strip()


def _validate_bucket_scope(bucket_scope: str) -> BucketScope:
    if bucket_scope not in {"public", "private"}:
        raise R2ArgumentError(
            "bucket_scope must be public or private",
            code="invalid_bucket_scope",
            context={"bucket_scope": bucket_scope},
        )
    return cast(BucketScope, bucket_scope)


def _validate_bucket_name_and_key(bucket_name: str, key: str) -> None:
    if not bucket_name.strip():
        raise R2ArgumentError(
            "bucket_name must not be empty",
            code="invalid_bucket_name",
        )
    if not key.strip():
        raise R2ArgumentError(
            "key must not be empty",
            code="invalid_key",
        )


def _validate_headers(content_type: str, cache_control: str) -> None:
    if not content_type.strip():
        raise R2ArgumentError(
            "content_type must not be empty",
            code="invalid_content_type",
        )
    if not cache_control.strip():
        raise R2ArgumentError(
            "cache_control must not be empty",
            code="invalid_cache_control",
        )


def _resolve_upload_body(plan: UploadPlan) -> bytes:
    has_bytes = plan.body_bytes is not None
    has_local_path = plan.local_path is not None
    if has_bytes == has_local_path:
        raise R2ArgumentError(
            "exactly one upload source must be provided",
            code="invalid_upload_source",
            context={
                "has_body_bytes": has_bytes,
                "has_local_path": has_local_path,
            },
        )

    if has_bytes:
        assert plan.body_bytes is not None
        return plan.body_bytes

    assert plan.local_path is not None
    path = Path(plan.local_path)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise R2ArgumentError(
            "failed to read upload file",
            code="invalid_local_path",
            context={"path_name": path.name, "path_depth": len(path.parts)},
        ) from exc


def _is_not_found(exc: ClientError) -> bool:
    response = cast(dict[str, object], exc.response)
    error_obj = response.get("Error", {})
    if isinstance(error_obj, dict):
        raw_code = error_obj.get("Code")
        if isinstance(raw_code, str) and raw_code in {"404", "NoSuchKey", "NotFound"}:
            return True

    metadata_obj = response.get("ResponseMetadata", {})
    if isinstance(metadata_obj, dict):
        raw_status = metadata_obj.get("HTTPStatusCode")
        if raw_status == 404:
            return True
    return False
