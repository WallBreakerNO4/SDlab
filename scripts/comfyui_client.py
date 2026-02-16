from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import ParseResult, quote, urlparse, urlunparse

import requests
import websocket


class ComfyUIClientError(RuntimeError):
    code: str
    context: dict[str, object]

    def __init__(
        self,
        message: str,
        *,
        code: str,
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})

    def as_metadata(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": str(self),
            "context": self.context,
        }


class ComfyUIRequestError(ComfyUIClientError):
    pass


class ComfyUIJobTimeoutError(ComfyUIClientError):
    pass


class WebSocketLike(Protocol):
    def settimeout(self, timeout: float) -> None: ...

    def recv(self) -> object: ...


def comfy_build_ws_url(base_url: str, client_id: str) -> str:
    parsed = _parse_base_url(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path_prefix = parsed.path.rstrip("/")
    ws_path = f"{path_prefix}/ws" if path_prefix else "/ws"
    query = f"clientId={quote(client_id, safe='')}"
    return urlunparse((scheme, parsed.netloc, ws_path, "", query, ""))


def comfy_submit_prompt(
    base_url: str,
    workflow: dict[str, object],
    client_id: str,
    request_timeout_s: float = 30.0,
) -> str:
    url = _build_http_url(base_url, "prompt")
    payload: dict[str, object] = {"prompt": workflow, "client_id": client_id}
    response = _request(
        "POST", url, request_timeout_s=request_timeout_s, json_payload=payload
    )
    body = _response_json_dict(response, endpoint="/prompt")

    prompt_id = body.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id:
        prompt_id = body.get("promptId")

    if not isinstance(prompt_id, str) or not prompt_id:
        keys = sorted(body.keys())
        raise ComfyUIClientError(
            "submit response missing prompt id",
            code="submit_missing_prompt_id",
            context={"response_keys": keys},
        )

    return prompt_id


def comfy_ws_connect(
    base_url: str,
    client_id: str | None = None,
    request_timeout_s: float = 30.0,
) -> websocket.WebSocket:
    resolved_client_id = client_id or str(uuid.uuid4())
    ws_url = comfy_build_ws_url(base_url, resolved_client_id)

    try:
        ws: websocket.WebSocket = websocket.create_connection(  # pyright: ignore[reportUnknownMemberType]
            ws_url,
            timeout=request_timeout_s,
        )
        ws.settimeout(request_timeout_s)
        return ws
    except Exception as exc:
        raise ComfyUIRequestError(
            "websocket connect failed",
            code="ws_connect_failed",
            context={"url": ws_url},
        ) from exc


def comfy_ws_wait_prompt_done(
    ws: WebSocketLike,
    prompt_id: str,
    request_timeout_s: float = 30.0,
    job_timeout_s: float = 600.0,
) -> None:
    if job_timeout_s <= 0:
        raise ComfyUIClientError(
            "job timeout must be positive",
            code="invalid_job_timeout",
            context={"job_timeout_s": job_timeout_s},
        )

    ws.settimeout(request_timeout_s)
    started_at = time.monotonic()

    while True:
        elapsed = time.monotonic() - started_at
        if elapsed >= job_timeout_s:
            raise ComfyUIJobTimeoutError(
                f"job timeout while waiting prompt {prompt_id}",
                code="job_timeout",
                context={
                    "prompt_id": prompt_id,
                    "job_timeout_s": job_timeout_s,
                    "elapsed_s": round(elapsed, 3),
                },
            )

        try:
            frame = ws.recv()
        except websocket.WebSocketTimeoutException:
            continue
        except Exception as exc:
            raise ComfyUIClientError(
                "websocket receive failed",
                code="ws_receive_failed",
                context={"prompt_id": prompt_id},
            ) from exc

        if not isinstance(frame, str):
            continue

        try:
            message_obj = cast(object, json.loads(frame))
        except json.JSONDecodeError:
            continue

        if not isinstance(message_obj, dict):
            continue

        message = cast(dict[str, object], message_obj)
        if _is_done_message(message, prompt_id):
            return


def comfy_get_history_item(
    base_url: str,
    prompt_id: str,
    request_timeout_s: float = 30.0,
) -> dict[str, object]:
    url = _build_http_url(base_url, f"history/{prompt_id}")
    response = _request("GET", url, request_timeout_s=request_timeout_s)
    body = _response_json_dict(response, endpoint="/history/{prompt_id}")

    wrapped = body.get(prompt_id)
    if isinstance(wrapped, dict):
        return cast(dict[str, object], wrapped)
    return body


def comfy_build_view_params(image: dict[str, object]) -> dict[str, str]:
    filename_obj = image.get("filename")
    if not isinstance(filename_obj, str) or not filename_obj:
        raise ComfyUIClientError(
            "image filename is required",
            code="view_missing_filename",
        )

    params: dict[str, str] = {"filename": filename_obj}

    subfolder_obj = image.get("subfolder")
    if isinstance(subfolder_obj, str) and subfolder_obj:
        params["subfolder"] = subfolder_obj

    image_type_obj = image.get("type")
    if isinstance(image_type_obj, str) and image_type_obj:
        params["type"] = image_type_obj
    else:
        params["type"] = "output"

    return params


def comfy_download_image_bytes(
    base_url: str,
    image: dict[str, object],
    request_timeout_s: float = 30.0,
) -> bytes:
    url = _build_http_url(base_url, "view")
    params = comfy_build_view_params(image)
    response = _request("GET", url, request_timeout_s=request_timeout_s, params=params)
    return response.content


def comfy_download_image_to_path(
    base_url: str,
    image: dict[str, object],
    output_path: str | Path,
    request_timeout_s: float = 30.0,
) -> Path:
    data = comfy_download_image_bytes(
        base_url=base_url,
        image=image,
        request_timeout_s=request_timeout_s,
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_bytes(data)
    return path


def _parse_base_url(base_url: str) -> ParseResult:
    normalized = base_url.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ComfyUIClientError(
            "invalid base url",
            code="invalid_base_url",
            context={"base_url": base_url},
        )
    return parsed


def _build_http_url(base_url: str, endpoint: str) -> str:
    parsed = _parse_base_url(base_url)
    path_prefix = parsed.path.rstrip("/")
    target_path = f"{path_prefix}/{endpoint}" if path_prefix else f"/{endpoint}"
    return urlunparse((parsed.scheme, parsed.netloc, target_path, "", "", ""))


def _request(
    method: str,
    url: str,
    *,
    request_timeout_s: float,
    json_payload: dict[str, object] | None = None,
    params: dict[str, str] | None = None,
) -> requests.Response:
    try:
        if method == "POST":
            response = requests.post(url, json=json_payload, timeout=request_timeout_s)
        elif method == "GET":
            response = requests.get(url, timeout=request_timeout_s, params=params)
        else:
            raise ValueError(f"unsupported method: {method}")
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise ComfyUIRequestError(
            "http request failed",
            code="http_request_failed",
            context={"method": method, "url": url},
        ) from exc


def _response_json_dict(
    response: requests.Response, *, endpoint: str
) -> dict[str, object]:
    try:
        body_obj = cast(object, response.json())
    except ValueError as exc:
        raise ComfyUIClientError(
            "invalid json response",
            code="invalid_json_response",
            context={"endpoint": endpoint},
        ) from exc

    if not isinstance(body_obj, dict):
        raise ComfyUIClientError(
            "json response must be an object",
            code="invalid_json_shape",
            context={"endpoint": endpoint},
        )

    return cast(dict[str, object], body_obj)


def _is_done_message(message: dict[str, object], prompt_id: str) -> bool:
    message_type = message.get("type")
    data_obj = message.get("data")
    if not isinstance(data_obj, dict):
        return False
    data = cast(dict[str, object], data_obj)

    message_prompt_id = data.get("prompt_id")
    if not isinstance(message_prompt_id, str) or message_prompt_id != prompt_id:
        return False

    if message_type == "executing" and data.get("node") is None:
        return True

    if message_type == "execution_success":
        return True

    return False
