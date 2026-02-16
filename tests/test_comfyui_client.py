# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
import requests
from websocket import WebSocketTimeoutException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.comfyui_client as comfy


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
            raise requests.HTTPError(f"HTTP {self.status_code}")


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

    monkeypatch.setattr("scripts.comfyui_client.requests.post", fake_post)

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

    monkeypatch.setattr("scripts.comfyui_client.requests.post", fake_post)

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
        "scripts.comfyui_client.websocket.create_connection", fake_create_connection
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
    monkeypatch.setattr("scripts.comfyui_client.time.monotonic", clock)

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

    monkeypatch.setattr("scripts.comfyui_client.requests.get", fake_get)

    item = comfy.comfy_get_history_item(
        base_url="http://127.0.0.1:8188/",
        prompt_id="p-1",
        request_timeout_s=8.0,
    )

    assert item == {"outputs": {"10": {"images": [{"filename": "a.png"}]}}}
    assert captured["url"] == "http://127.0.0.1:8188/history/p-1"
    assert captured["timeout"] == 8.0
    assert captured["params"] is None


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

    monkeypatch.setattr("scripts.comfyui_client.requests.get", fake_get)

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
    def fake_get(url: str, timeout: float, params: dict[str, str]) -> MockResponse:
        _ = (url, timeout, params)
        return MockResponse(content=b"image-bytes")

    monkeypatch.setattr("scripts.comfyui_client.requests.get", fake_get)

    output_path = tmp_path / "out.png"
    saved_path = comfy.comfy_download_image_to_path(
        base_url="http://127.0.0.1:8188",
        image={"filename": "x.png"},
        output_path=output_path,
        request_timeout_s=2.0,
    )

    assert saved_path == output_path
    assert output_path.read_bytes() == b"image-bytes"
