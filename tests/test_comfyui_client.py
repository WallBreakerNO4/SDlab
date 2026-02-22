# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
import requests
from websocket import WebSocketTimeoutException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.generation.comfyui_client as comfy


class MockResponse:
    _json_data: object | None
    content: bytes
    status_code: int

    def __init__(
        self,
        *,
        json_data: object | None = None,
        content: bytes = b"",
        status_code: int = 200,
    ) -> None:
        self._json_data = json_data
        self.content = content
        self.status_code = status_code

    def json(self) -> object:
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}",
                response=cast(requests.Response, cast(object, self)),
            )


class MockStreamResponse(MockResponse):
    _chunks: list[bytes]
    _iter_error: BaseException | None

    def __init__(
        self,
        *,
        chunks: list[bytes],
        iter_error: BaseException | None = None,
        status_code: int = 200,
    ) -> None:
        super().__init__(status_code=status_code)
        self._chunks = list(chunks)
        self._iter_error = iter_error

    def iter_content(self, chunk_size: int = 1) -> Iterator[bytes]:
        _ = chunk_size
        for chunk in self._chunks:
            yield chunk
        if self._iter_error is not None:
            raise self._iter_error


class FakeWebSocket:
    _messages: list[object]
    timeout: float | None
    closed: bool

    def __init__(self, messages: list[object]) -> None:
        self._messages = list(messages)
        self.timeout = None
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def recv(self) -> object:
        if not self._messages:
            raise WebSocketTimeoutException("read timeout")
        item = self._messages.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self) -> None:
        self.closed = True


class ControlledClock:
    _values: Iterator[float]
    _last: float

    def __init__(self, values: list[float]) -> None:
        self._values = iter(values)
        self._last = values[-1]

    def __call__(self) -> float:
        try:
            self._last = next(self._values)
        except StopIteration:
            pass
        return self._last


class MutableClock:
    now: float

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.parametrize("id_key", ["prompt_id", "promptId"])
def test_comfy_submit_prompt_accepts_prompt_id_and_promptId(
    monkeypatch: pytest.MonkeyPatch, id_key: str
) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, json: object, timeout: float) -> MockResponse:  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return MockResponse(json_data={id_key: "p-123"})

    monkeypatch.setattr("scripts.generation.comfyui_client.requests.post", fake_post)

    prompt_id = comfy.comfy_submit_prompt(
        base_url="http://127.0.0.1:8188/",
        workflow={"1": {"class_type": "KSampler"}},
        client_id="cid",
        request_timeout_s=5.0,
    )

    assert prompt_id == "p-123"
    assert captured["url"] == "http://127.0.0.1:8188/prompt"
    assert captured["timeout"] == 5.0
    assert captured["json"] == {
        "prompt": {"1": {"class_type": "KSampler"}},
        "client_id": "cid",
    }


def test_comfy_submit_prompt_raises_structured_error_when_prompt_id_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url: str, json: object, timeout: float) -> MockResponse:  # noqa: A002
        _ = (url, json, timeout)
        return MockResponse(json_data={"status": "ok"})

    monkeypatch.setattr("scripts.generation.comfyui_client.requests.post", fake_post)

    with pytest.raises(comfy.ComfyUIClientError) as exc:
        _ = comfy.comfy_submit_prompt(
            base_url="http://127.0.0.1:8188",
            workflow={"1": {}},
            client_id="cid",
        )

    message = str(exc.value)
    assert "prompt" in message.lower()
    assert "COMFYUI_" not in message
    assert len(message) < 300


def test_comfy_ws_connect_uses_clientId_query_and_preserves_base_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    fake_ws = FakeWebSocket([])

    def fake_create_connection(url: str, timeout: float) -> FakeWebSocket:
        captured["url"] = url
        captured["timeout"] = timeout
        return fake_ws

    monkeypatch.setattr(
        "scripts.generation.comfyui_client.websocket.create_connection",
        fake_create_connection,
    )

    ws = comfy.comfy_ws_connect(
        base_url="https://demo.local/comfy/api/",
        client_id="client 42",
        request_timeout_s=12.5,
    )

    assert ws is fake_ws
    assert captured["url"] == "wss://demo.local/comfy/api/ws?clientId=client%2042"
    assert captured["timeout"] == 12.5
    assert fake_ws.timeout == 12.5


def test_comfy_ws_wait_prompt_done_supports_executing_done_and_ignores_noise() -> None:
    ws = FakeWebSocket(
        messages=[
            b"\x00\x01preview",
            "not-json",
            json.dumps(
                {
                    "type": "executing",
                    "data": {"prompt_id": "other", "node": None},
                }
            ),
            json.dumps(
                {
                    "type": "executing",
                    "data": {"prompt_id": "p-123", "node": "7"},
                }
            ),
            json.dumps(
                {
                    "type": "executing",
                    "data": {"prompt_id": "p-123", "node": None},
                }
            ),
        ]
    )

    comfy.comfy_ws_wait_prompt_done(
        ws=ws,
        prompt_id="p-123",
        request_timeout_s=0.25,
        job_timeout_s=3.0,
    )

    assert ws.timeout == 0.25


def test_comfy_ws_wait_prompt_done_supports_execution_success_fallback() -> None:
    ws = FakeWebSocket(
        messages=[
            json.dumps(
                {
                    "type": "execution_success",
                    "data": {"prompt_id": "p-abc"},
                }
            )
        ]
    )

    comfy.comfy_ws_wait_prompt_done(
        ws=ws,
        prompt_id="p-abc",
        request_timeout_s=0.5,
        job_timeout_s=1.5,
    )


def test_comfy_ws_wait_prompt_done_raises_execution_error_for_current_prompt() -> None:
    ws = FakeWebSocket(
        messages=[
            json.dumps(
                {
                    "type": "execution_error",
                    "data": {
                        "prompt_id": "p-err",
                        "node_id": "17",
                        "node_type": "KSampler",
                        "exception_type": "RuntimeError",
                        "exception_message": "latent shape mismatch",
                        "traceback": ["line1", "line2"],
                    },
                }
            )
        ]
    )

    with pytest.raises(comfy.ComfyUIClientError) as exc:
        comfy.comfy_ws_wait_prompt_done(
            ws=ws,
            prompt_id="p-err",
            request_timeout_s=0.2,
            job_timeout_s=1.0,
        )

    err = exc.value
    assert err.code == "execution_error"
    assert "p-err" in str(err)
    _ = json.dumps(err.context)


def test_comfy_ws_wait_prompt_done_raises_execution_interrupted_for_current_prompt() -> (
    None
):
    ws = FakeWebSocket(
        messages=[
            json.dumps(
                {
                    "type": "execution_interrupted",
                    "data": {
                        "prompt_id": "p-stop",
                        "node_id": "4",
                        "node_type": "KSampler",
                    },
                }
            )
        ]
    )

    with pytest.raises(comfy.ComfyUIClientError) as exc:
        comfy.comfy_ws_wait_prompt_done(
            ws=ws,
            prompt_id="p-stop",
            request_timeout_s=0.2,
            job_timeout_s=1.0,
        )

    err = exc.value
    assert err.code == "execution_interrupted"
    assert "p-stop" in str(err)
    _ = json.dumps(err.context)


def test_comfy_ws_wait_prompt_done_ignores_other_prompt_execution_error() -> None:
    ws = FakeWebSocket(
        messages=[
            json.dumps(
                {
                    "type": "execution_error",
                    "data": {
                        "prompt_id": "other-prompt",
                        "node_id": "9",
                        "exception_message": "should be ignored",
                    },
                }
            ),
            json.dumps(
                {
                    "type": "execution_success",
                    "data": {"prompt_id": "p-ok"},
                }
            ),
        ]
    )

    comfy.comfy_ws_wait_prompt_done(
        ws=ws,
        prompt_id="p-ok",
        request_timeout_s=0.2,
        job_timeout_s=1.0,
    )


def test_comfy_ws_wait_prompt_done_retries_request_timeout_until_job_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = FakeWebSocket(
        messages=[
            WebSocketTimeoutException("read timeout"),
            WebSocketTimeoutException("read timeout"),
            WebSocketTimeoutException("read timeout"),
        ]
    )
    clock = ControlledClock([0.0, 0.3, 0.7, 1.2, 1.4])
    monkeypatch.setattr("scripts.generation.comfyui_client.time.monotonic", clock)

    with pytest.raises(comfy.ComfyUIJobTimeoutError) as exc:
        comfy.comfy_ws_wait_prompt_done(
            ws=ws,
            prompt_id="p-timeout",
            request_timeout_s=0.1,
            job_timeout_s=1.0,
        )

    message = str(exc.value)
    assert "p-timeout" in message
    assert "job" in message.lower()


def test_wait_prompt_done_with_fallback_recovers_from_ws_receive_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = FakeWebSocket(messages=[Exception("socket read failed")])
    history_payloads = [
        {"p-fallback": {"outputs": {"10": {"images": []}}}},
        {"p-fallback": {"outputs": {"10": {"images": [{"filename": "a.png"}]}}}},
    ]
    attempts = 0
    submit_calls = 0
    clock = MutableClock(now=0.0)

    def fake_submit_prompt(*args: object, **kwargs: object) -> str:
        nonlocal submit_calls
        submit_calls += 1
        _ = (args, kwargs)
        return "unexpected"

    def fake_get(
        url: str, timeout: float, params: object | None = None
    ) -> MockResponse:
        nonlocal attempts
        attempts += 1
        _ = (url, timeout, params)
        return MockResponse(json_data=history_payloads[min(attempts - 1, 1)])

    def fake_ws_connect(*args: object, **kwargs: object) -> FakeWebSocket:
        _ = (args, kwargs)
        return ws

    monkeypatch.setattr(comfy, "comfy_submit_prompt", fake_submit_prompt)
    monkeypatch.setattr(comfy, "comfy_ws_connect", fake_ws_connect)
    monkeypatch.setattr("scripts.generation.comfyui_client.requests.get", fake_get)
    monkeypatch.setattr(
        "scripts.generation.comfyui_client.time.monotonic", clock.monotonic
    )
    monkeypatch.setattr("scripts.generation.comfyui_client.time.sleep", clock.sleep)

    comfy.comfy_wait_prompt_done_with_fallback(
        base_url="http://127.0.0.1:8188",
        client_id="cid",
        prompt_id="p-fallback",
        request_timeout_s=0.1,
        job_timeout_s=3.0,
    )

    assert attempts == 2
    assert submit_calls == 0


def test_wait_prompt_done_with_fallback_recovers_from_ws_connect_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history_payloads = [
        {"p-fallback": {"outputs": {"10": {"images": []}}}},
        {"p-fallback": {"outputs": {"10": {"images": [{"filename": "a.png"}]}}}},
    ]
    attempts = 0
    clock = MutableClock(now=0.0)

    def fake_get(
        url: str, timeout: float, params: object | None = None
    ) -> MockResponse:
        nonlocal attempts
        attempts += 1
        _ = (url, timeout, params)
        return MockResponse(json_data=history_payloads[min(attempts - 1, 1)])

    def fake_ws_connect(*args: object, **kwargs: object) -> FakeWebSocket:
        _ = (args, kwargs)
        raise comfy.ComfyUIRequestError(
            "websocket connect failed",
            code="ws_connect_failed",
            context={"url": "ws://127.0.0.1:8188/ws"},
        )

    monkeypatch.setattr(comfy, "comfy_ws_connect", fake_ws_connect)
    monkeypatch.setattr("scripts.generation.comfyui_client.requests.get", fake_get)
    monkeypatch.setattr(
        "scripts.generation.comfyui_client.time.monotonic", clock.monotonic
    )
    monkeypatch.setattr("scripts.generation.comfyui_client.time.sleep", clock.sleep)

    comfy.comfy_wait_prompt_done_with_fallback(
        base_url="http://127.0.0.1:8188",
        client_id="cid",
        prompt_id="p-fallback",
        request_timeout_s=0.1,
        job_timeout_s=3.0,
    )

    assert attempts == 2


def test_wait_prompt_done_with_fallback_raises_job_timeout_when_history_never_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    clock = MutableClock(now=0.0)

    def fake_get(
        url: str, timeout: float, params: object | None = None
    ) -> MockResponse:
        nonlocal attempts
        attempts += 1
        _ = (url, timeout, params)
        return MockResponse(
            json_data={"p-timeout": {"outputs": {"10": {"images": []}}}}
        )

    def fake_ws_connect(*args: object, **kwargs: object) -> FakeWebSocket:
        _ = (args, kwargs)
        raise comfy.ComfyUIRequestError(
            "websocket connect failed",
            code="ws_connect_failed",
        )

    monkeypatch.setattr(comfy, "comfy_ws_connect", fake_ws_connect)
    monkeypatch.setattr("scripts.generation.comfyui_client.requests.get", fake_get)
    monkeypatch.setattr(
        "scripts.generation.comfyui_client.time.monotonic", clock.monotonic
    )
    monkeypatch.setattr("scripts.generation.comfyui_client.time.sleep", clock.sleep)

    with pytest.raises(comfy.ComfyUIClientError) as exc:
        comfy.comfy_wait_prompt_done_with_fallback(
            base_url="http://127.0.0.1:8188",
            client_id="cid",
            prompt_id="p-timeout",
            request_timeout_s=0.1,
            job_timeout_s=0.6,
        )

    assert exc.value.code == "job_timeout"
    _ = json.dumps(exc.value.context)
    assert attempts >= 2


@pytest.mark.parametrize(
    "history_payload",
    [
        {"p-1": {"outputs": {"10": {"images": [{"filename": "a.png"}]}}}},
        {"outputs": {"10": {"images": [{"filename": "a.png"}]}}},
    ],
)
def test_comfy_get_history_item_supports_response_compatibility(
    monkeypatch: pytest.MonkeyPatch, history_payload: dict[str, object]
) -> None:
    captured: dict[str, object] = {}

    def fake_get(
        url: str, timeout: float, params: object | None = None
    ) -> MockResponse:
        captured["url"] = url
        captured["timeout"] = timeout
        captured["params"] = params
        return MockResponse(json_data=history_payload)

    monkeypatch.setattr("scripts.generation.comfyui_client.requests.get", fake_get)

    item = comfy.comfy_get_history_item(
        base_url="http://127.0.0.1:8188/",
        prompt_id="p-1",
        request_timeout_s=8.0,
    )

    assert item == {"outputs": {"10": {"images": [{"filename": "a.png"}]}}}
    assert captured["url"] == "http://127.0.0.1:8188/history/p-1"
    assert captured["timeout"] == 8.0
    assert captured["params"] is None


def test_comfy_get_history_item_retries_transient_http_status_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def fake_get(
        url: str, timeout: float, params: object | None = None
    ) -> MockResponse:
        nonlocal attempts
        attempts += 1
        _ = (url, timeout, params)
        if attempts < 3:
            return MockResponse(status_code=503)
        return MockResponse(json_data={"p-1": {"outputs": {}}})

    monkeypatch.setattr("scripts.generation.comfyui_client.requests.get", fake_get)
    monkeypatch.setattr("scripts.generation.retry.random.random", lambda: 0.0)

    item = comfy.comfy_get_history_item(
        base_url="http://127.0.0.1:8188",
        prompt_id="p-1",
        request_timeout_s=1.0,
    )

    assert attempts == 3
    assert item == {"outputs": {}}


def test_comfy_get_history_item_retries_connection_error_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def fake_get(
        url: str, timeout: float, params: object | None = None
    ) -> MockResponse:
        nonlocal attempts
        attempts += 1
        _ = (url, timeout, params)
        if attempts < 3:
            raise requests.ConnectionError("connection dropped")
        return MockResponse(json_data={"outputs": {"10": {}}})

    monkeypatch.setattr("scripts.generation.comfyui_client.requests.get", fake_get)
    monkeypatch.setattr("scripts.generation.retry.random.random", lambda: 0.0)

    item = comfy.comfy_get_history_item(
        base_url="http://127.0.0.1:8188",
        prompt_id="p-conn",
    )

    assert attempts == 3
    assert item == {"outputs": {"10": {}}}


def test_comfy_get_history_item_does_not_retry_http_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def fake_get(
        url: str, timeout: float, params: object | None = None
    ) -> MockResponse:
        nonlocal attempts
        attempts += 1
        _ = (url, timeout, params)
        return MockResponse(status_code=404)

    monkeypatch.setattr("scripts.generation.comfyui_client.requests.get", fake_get)
    monkeypatch.setattr("scripts.generation.retry.random.random", lambda: 0.0)

    with pytest.raises(comfy.ComfyUIRequestError) as exc:
        _ = comfy.comfy_get_history_item(
            base_url="http://127.0.0.1:8188",
            prompt_id="p-404",
            request_timeout_s=1.0,
        )

    assert attempts == 1
    assert exc.value.context["status_code"] == 404


def test_comfy_get_history_item_transient_retry_stops_after_total_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    clock = MutableClock(now=0.0)

    def fake_get(
        url: str, timeout: float, params: object | None = None
    ) -> MockResponse:
        nonlocal attempts
        attempts += 1
        _ = (url, timeout, params)
        raise requests.Timeout("read timeout")

    monkeypatch.setattr("scripts.generation.comfyui_client.requests.get", fake_get)
    monkeypatch.setattr(comfy, "HISTORY_GET_RETRY_MAX_ATTEMPTS", 99)
    monkeypatch.setattr(comfy, "HISTORY_GET_RETRY_STOP_AFTER_DELAY_S", 0.3)
    monkeypatch.setattr("scripts.generation.retry.time.monotonic", clock.monotonic)
    monkeypatch.setattr("scripts.generation.retry.time.sleep", clock.sleep)
    monkeypatch.setattr("scripts.generation.retry.random.random", lambda: 1.0)

    with pytest.raises(comfy.ComfyUITransientRequestError) as exc:
        _ = comfy.comfy_get_history_item(
            base_url="http://127.0.0.1:8188",
            prompt_id="p-budget",
            request_timeout_s=1.0,
        )

    assert attempts == 3
    assert exc.value.context["method"] == "GET"
    assert exc.value.context["url"] == "http://127.0.0.1:8188/history/p-budget"


def test_comfy_build_view_params_defaults_type_and_validates_filename() -> None:
    params = comfy.comfy_build_view_params(
        {"filename": "img.png", "subfolder": "foo/bar"}
    )

    assert params == {
        "filename": "img.png",
        "subfolder": "foo/bar",
        "type": "output",
    }

    with pytest.raises(comfy.ComfyUIClientError):
        _ = comfy.comfy_build_view_params({"subfolder": "foo"})


def test_comfy_download_image_bytes_calls_view_endpoint_with_query_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, timeout: float, params: dict[str, str]) -> MockResponse:
        captured["url"] = url
        captured["timeout"] = timeout
        captured["params"] = params
        return MockResponse(content=b"PNGDATA")

    monkeypatch.setattr("scripts.generation.comfyui_client.requests.get", fake_get)

    image_bytes = comfy.comfy_download_image_bytes(
        base_url="http://127.0.0.1:8188",
        image={"filename": "sample.png", "subfolder": "job42", "type": "temp"},
        request_timeout_s=6.0,
    )

    assert image_bytes == b"PNGDATA"
    assert captured["url"] == "http://127.0.0.1:8188/view"
    assert captured["timeout"] == 6.0
    assert captured["params"] == {
        "filename": "sample.png",
        "subfolder": "job42",
        "type": "temp",
    }


def test_comfy_download_image_to_path_saves_downloaded_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_get(
        url: str,
        timeout: float,
        params: dict[str, str],
        stream: bool = False,
    ) -> MockResponse:
        _ = (url, timeout, params, stream)
        return MockStreamResponse(chunks=[b"image-bytes"])

    monkeypatch.setattr("scripts.generation.comfyui_client.requests.get", fake_get)

    output_path = tmp_path / "out.png"
    saved_path = comfy.comfy_download_image_to_path(
        base_url="http://127.0.0.1:8188",
        image={"filename": "x.png"},
        output_path=output_path,
        request_timeout_s=2.0,
    )

    assert saved_path == output_path
    assert output_path.read_bytes() == b"image-bytes"


def test_view_download_retries_404_and_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    attempts = 0

    def fake_get(
        url: str,
        timeout: float,
        params: dict[str, str],
        stream: bool = False,
    ) -> MockResponse:
        nonlocal attempts
        attempts += 1
        _ = (url, timeout, params, stream)
        if attempts == 1:
            return MockResponse(status_code=404)
        return MockStreamResponse(chunks=[b"hello", b"-", b"world"])

    monkeypatch.setattr("scripts.generation.comfyui_client.requests.get", fake_get)
    monkeypatch.setattr("scripts.generation.retry.random.random", lambda: 0.0)

    output_path = tmp_path / "view-404-retry.png"
    saved_path = comfy.comfy_download_image_to_path(
        base_url="http://127.0.0.1:8188",
        image={"filename": "x.png"},
        output_path=output_path,
        request_timeout_s=1.0,
    )

    assert attempts == 2
    assert saved_path == output_path
    assert output_path.read_bytes() == b"hello-world"


def test_view_download_stream_interrupted_cleans_temp_and_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_get(
        url: str,
        timeout: float,
        params: dict[str, str],
        stream: bool = False,
    ) -> MockResponse:
        _ = (url, timeout, params, stream)
        return MockStreamResponse(
            chunks=[b"part"],
            iter_error=requests.exceptions.ChunkedEncodingError("stream broken"),
        )

    monkeypatch.setattr("scripts.generation.comfyui_client.requests.get", fake_get)
    monkeypatch.setattr("scripts.generation.retry.random.random", lambda: 0.0)
    monkeypatch.setattr(comfy, "VIEW_GET_RETRY_MAX_ATTEMPTS", 1)

    output_dir = tmp_path / "atomic-download"
    output_path = output_dir / "broken.png"

    with pytest.raises(comfy.ComfyUITransientRequestError) as exc:
        _ = comfy.comfy_download_image_to_path(
            base_url="http://127.0.0.1:8188",
            image={"filename": "x.png"},
            output_path=output_path,
            request_timeout_s=1.0,
        )

    assert exc.value.code == "http_request_failed"
    assert not output_path.exists()
    assert output_dir.exists()
    assert list(output_dir.iterdir()) == []


def test_view_download_does_not_retry_http_400(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    attempts = 0

    def fake_get(
        url: str,
        timeout: float,
        params: dict[str, str],
        stream: bool = False,
    ) -> MockResponse:
        nonlocal attempts
        attempts += 1
        _ = (url, timeout, params, stream)
        return MockResponse(status_code=400)

    monkeypatch.setattr("scripts.generation.comfyui_client.requests.get", fake_get)
    monkeypatch.setattr("scripts.generation.retry.random.random", lambda: 0.0)

    with pytest.raises(comfy.ComfyUIRequestError) as exc:
        _ = comfy.comfy_download_image_to_path(
            base_url="http://127.0.0.1:8188",
            image={"filename": "x.png"},
            output_path=tmp_path / "bad-request.png",
            request_timeout_s=1.0,
        )

    assert attempts == 1
    assert exc.value.code == "http_request_failed"
    assert exc.value.context["status_code"] == 400
