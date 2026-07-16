# pyright: basic, reportMissingImports=false

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import cast

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError
from botocore.response import StreamingBody
from botocore.stub import Stubber

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.r2_upload.r2_client import (
    R2ArgumentError,
    R2AuthError,
    R2Client,
    R2ConfigError,
    R2RemoteError,
    R2RetryExhaustedError,
    S3ClientLike,
    UploadPlan,
)


def _make_s3_client() -> S3ClientLike:
    return cast(
        S3ClientLike,
        boto3.client(
            "s3",
            endpoint_url="https://example.invalid",
            aws_access_key_id="test-ak",
            aws_secret_access_key="test-sk",
            region_name="auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 0}),
        ),
    )


def test_from_env_builds_boto3_client_with_required_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_client(service_name: str, **kwargs: object) -> object:
        captured["service_name"] = service_name
        captured.update(kwargs)
        return sentinel

    monkeypatch.setenv("R2_ENDPOINT", "https://example.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "sk")
    monkeypatch.setattr("scripts.r2_upload.r2_client.boto3.client", fake_client)

    client = R2Client.from_env(dry_run=False)

    assert captured["service_name"] == "s3"
    assert captured["endpoint_url"] == "https://example.r2.cloudflarestorage.com"
    assert captured["region_name"] == "auto"
    assert captured["aws_access_key_id"] == "ak"
    assert captured["aws_secret_access_key"] == "sk"
    assert isinstance(captured["config"], Config)
    assert getattr(captured["config"], "signature_version", None) == "s3v4"
    assert client._s3_client is sentinel


def test_from_env_dry_run_does_not_construct_boto3_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_client(*args: object, **kwargs: object) -> object:
        _ = args
        _ = kwargs
        raise AssertionError("dry-run should not construct boto3 client")

    monkeypatch.setattr("scripts.r2_upload.r2_client.boto3.client", fail_client)
    monkeypatch.delenv("R2_ENDPOINT", raising=False)
    monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)

    client = R2Client.from_env(dry_run=True)

    assert client.dry_run is True
    assert client._s3_client is None


def test_from_env_missing_required_variable_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("R2_ENDPOINT", raising=False)
    monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)

    with pytest.raises(R2ConfigError) as exc:
        _ = R2Client.from_env(dry_run=False)

    assert exc.value.category == "config"
    assert exc.value.code == "missing_env"
    assert exc.value.context["missing_env"] == "R2_ENDPOINT"


def test_head_exists_true_when_remote_object_exists() -> None:
    s3_client = _make_s3_client()
    stubber = Stubber(s3_client)
    stubber.add_response(
        "head_object",
        service_response={"ContentLength": 3},
        expected_params={"Bucket": "sdslab-public", "Key": "runs/a.webp"},
    )

    with stubber:
        client = R2Client(s3_client=s3_client, dry_run=False, max_retries=0)
        assert (
            client.head_exists("sdslab-public", "runs/a.webp", bucket_scope="public")
            is True
        )


def test_head_exists_false_when_remote_object_not_found() -> None:
    s3_client = _make_s3_client()
    stubber = Stubber(s3_client)
    stubber.add_client_error(
        "head_object",
        service_error_code="404",
        http_status_code=404,
        expected_params={"Bucket": "sdslab-public", "Key": "runs/missing.webp"},
    )

    with stubber:
        client = R2Client(s3_client=s3_client, dry_run=False, max_retries=0)
        assert (
            client.head_exists(
                "sdslab-public", "runs/missing.webp", bucket_scope="public"
            )
            is False
        )


def test_read_bytes_if_exists_returns_object_body() -> None:
    s3_client = _make_s3_client()
    stubber = Stubber(s3_client)
    payload = b'{"release_id":"abc123"}'
    stubber.add_response(
        "get_object",
        service_response={
            "Body": StreamingBody(io.BytesIO(payload), len(payload)),
            "ContentLength": len(payload),
        },
        expected_params={
            "Bucket": "sdslab-public",
            "Key": "runs/run-a/view/current.json",
        },
    )

    with stubber:
        client = R2Client(s3_client=s3_client, dry_run=False, max_retries=0)
        assert (
            client.read_bytes_if_exists(
                "sdslab-public",
                "runs/run-a/view/current.json",
                bucket_scope="public",
            )
            == payload
        )


def test_read_bytes_if_exists_returns_none_when_missing() -> None:
    s3_client = _make_s3_client()
    stubber = Stubber(s3_client)
    stubber.add_client_error(
        "get_object",
        service_error_code="404",
        http_status_code=404,
        expected_params={
            "Bucket": "sdslab-public",
            "Key": "runs/run-a/view/current.json",
        },
    )

    with stubber:
        client = R2Client(s3_client=s3_client, dry_run=False, max_retries=0)
        assert (
            client.read_bytes_if_exists(
                "sdslab-public",
                "runs/run-a/view/current.json",
                bucket_scope="public",
            )
            is None
        )


def test_put_bytes_uses_explicit_content_type_and_cache_control() -> None:
    s3_client = _make_s3_client()
    stubber = Stubber(s3_client)
    plan = UploadPlan.from_variant(
        bucket_name="sdslab-public",
        bucket_scope="public",
        key="runs/r/display.webp",
        variant="display_webp",
        body_bytes=b"abc",
    )

    stubber.add_response(
        "put_object",
        service_response={"ETag": '"abc"'},
        expected_params={
            "Bucket": "sdslab-public",
            "Key": "runs/r/display.webp",
            "Body": b"abc",
            "ContentType": "image/webp",
            "CacheControl": "public, max-age=31536000, immutable",
        },
    )

    with stubber:
        client = R2Client(s3_client=s3_client, dry_run=False, max_retries=0)
        client.put_bytes(plan)


def test_put_bytes_supports_local_file_upload(tmp_path: Path) -> None:
    source = tmp_path / "image.avif"
    source.write_bytes(b"payload")

    s3_client = _make_s3_client()
    stubber = Stubber(s3_client)
    plan = UploadPlan.from_variant(
        bucket_name="sdslab-private",
        bucket_scope="private",
        key="runs/r/original.avif",
        variant="thumb_avif",
        local_path=source,
    )

    stubber.add_response(
        "put_object",
        service_response={"ETag": '"def"'},
        expected_params={
            "Bucket": "sdslab-private",
            "Key": "runs/r/original.avif",
            "Body": b"payload",
            "ContentType": "image/avif",
            "CacheControl": "private, max-age=0, no-cache",
        },
    )

    with stubber:
        client = R2Client(s3_client=s3_client, dry_run=False, max_retries=0)
        client.put_bytes(plan)


def test_dry_run_head_and_put_do_not_call_underlying_client() -> None:
    class FailClient:
        def head_object(self, **kwargs: object) -> dict[str, object]:
            _ = kwargs
            raise AssertionError("head_object should not be called in dry-run")

        def put_object(self, **kwargs: object) -> dict[str, object]:
            _ = kwargs
            raise AssertionError("put_object should not be called in dry-run")

    client = R2Client(s3_client=FailClient(), dry_run=True)
    plan = UploadPlan.from_variant(
        bucket_name="sdslab-public",
        bucket_scope="public",
        key="runs/r/thumb.webp",
        variant="thumb_webp",
        body_bytes=b"x",
    )

    assert client.head_exists("sdslab-public", "runs/r/thumb.webp") is False
    client.put_bytes(plan)


def test_put_bytes_invalid_source_raises_argument_error() -> None:
    client = R2Client(s3_client=None, dry_run=True)
    invalid_plan = UploadPlan(
        bucket_name="sdslab-public",
        bucket_scope="public",
        key="runs/r/img.webp",
        content_type="image/webp",
        cache_control="public, max-age=31536000, immutable",
    )

    with pytest.raises(R2ArgumentError) as exc:
        client.put_bytes(invalid_plan)

    assert exc.value.category == "argument"
    assert exc.value.code == "invalid_upload_source"


def test_put_bytes_auth_error_is_classified_without_secret_leak() -> None:
    s3_client = _make_s3_client()
    stubber = Stubber(s3_client)
    plan = UploadPlan.from_variant(
        bucket_name="sdslab-public",
        bucket_scope="public",
        key="runs/secret/raw.webp",
        variant="display_webp",
        body_bytes=b"x",
    )
    stubber.add_client_error(
        "put_object",
        service_error_code="AccessDenied",
        service_message="forbidden",
        http_status_code=403,
        expected_params={
            "Bucket": "sdslab-public",
            "Key": "runs/secret/raw.webp",
            "Body": b"x",
            "ContentType": "image/webp",
            "CacheControl": "public, max-age=31536000, immutable",
        },
    )

    with stubber:
        client = R2Client(s3_client=s3_client, dry_run=False, max_retries=0)
        with pytest.raises(R2AuthError) as exc:
            client.put_bytes(plan)

    assert exc.value.category == "auth"
    assert "runs/secret/raw.webp" not in str(exc.value)
    assert "public" not in str(exc.value)
    assert exc.value.context["bucket_scope"] == "public"
    assert "bucket_name" not in exc.value.context


def test_put_bytes_non_retryable_remote_error_is_classified() -> None:
    s3_client = _make_s3_client()
    stubber = Stubber(s3_client)
    plan = UploadPlan.from_variant(
        bucket_name="sdslab-private",
        bucket_scope="private",
        key="runs/r/file.webp",
        variant="display_webp",
        body_bytes=b"webp",
    )
    stubber.add_client_error(
        "put_object",
        service_error_code="ValidationError",
        service_message="bad request",
        http_status_code=400,
        expected_params={
            "Bucket": "sdslab-private",
            "Key": "runs/r/file.webp",
            "Body": b"webp",
            "ContentType": "image/webp",
            "CacheControl": "private, max-age=0, no-cache",
        },
    )

    with stubber:
        client = R2Client(s3_client=s3_client, dry_run=False, max_retries=0)
        with pytest.raises(R2RemoteError) as exc:
            client.put_bytes(plan)

    assert exc.value.category == "remote"
    assert exc.value.retryable is False


def test_put_bytes_retry_exhausted_after_network_errors() -> None:
    class NetworkFailClient:
        def head_object(self, **kwargs: object) -> dict[str, object]:
            _ = kwargs
            raise AssertionError("head_object is not used in this test")

        def put_object(self, **kwargs: object) -> dict[str, object]:
            _ = kwargs
            raise EndpointConnectionError(endpoint_url="https://redacted.invalid")

    sleeps: list[float] = []
    client = R2Client(
        s3_client=NetworkFailClient(),
        dry_run=False,
        max_retries=1,
        sleep_fn=sleeps.append,
    )
    plan = UploadPlan.from_variant(
        bucket_name="sdslab-private",
        bucket_scope="private",
        key="runs/private/item.webp",
        variant="thumb_webp",
        body_bytes=b"x",
    )

    with pytest.raises(R2RetryExhaustedError) as exc:
        client.put_bytes(plan)

    assert exc.value.category == "retry_exhausted"
    assert exc.value.context["attempts"] == 2
    assert exc.value.context["last_error_code"] == "network_error"
    assert sleeps == [0.15]


def test_put_bytes_retry_exhausted_after_rate_limit_errors() -> None:
    class RateLimitedClient:
        def __init__(self) -> None:
            self.calls = 0

        def head_object(self, **kwargs: object) -> dict[str, object]:
            _ = kwargs
            raise AssertionError("head_object is not used in this test")

        def put_object(self, **kwargs: object) -> dict[str, object]:
            _ = kwargs
            self.calls += 1
            raise ClientError(
                {
                    "Error": {"Code": "SlowDown", "Message": "slow down"},
                    "ResponseMetadata": {"HTTPStatusCode": 429},
                },
                "PutObject",
            )

    sleeps: list[float] = []
    low = RateLimitedClient()
    client = R2Client(
        s3_client=low,
        dry_run=False,
        max_retries=2,
        sleep_fn=sleeps.append,
    )
    plan = UploadPlan.from_variant(
        bucket_name="sdslab-public",
        bucket_scope="public",
        key="runs/pub/item.webp",
        variant="display_webp",
        body_bytes=b"y",
    )

    with pytest.raises(R2RetryExhaustedError) as exc:
        client.put_bytes(plan)

    assert exc.value.category == "retry_exhausted"
    assert exc.value.context["last_error_code"] == "rate_limited"
    assert low.calls == 3
    assert sleeps == [0.15, 0.3]
