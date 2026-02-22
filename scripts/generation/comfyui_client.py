from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import ParseResult, quote, urlparse, urlunparse

import requests
import websocket

from scripts.generation.retry import retry_call


LOG = logging.getLogger(__name__)


HISTORY_GET_RETRY_MAX_ATTEMPTS = 5
HISTORY_GET_RETRY_STOP_AFTER_DELAY_S = 10.0
_HISTORY_GET_RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})
VIEW_GET_RETRY_MAX_ATTEMPTS = 5
VIEW_GET_RETRY_STOP_AFTER_DELAY_S = 15.0
_VIEW_GET_RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})
HISTORY_FALLBACK_POLL_INTERVAL_S = 0.25


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


class ComfyUITransientRequestError(ComfyUIRequestError):
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
        _raise_if_terminal_error(message, prompt_id)
        if _is_done_message(message, prompt_id):
            return


def comfy_wait_prompt_done_with_fallback(
    base_url: str,
    client_id: str,
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

    started_at = time.monotonic()
    ws: websocket.WebSocket | None = None

    try:
        ws = comfy_ws_connect(
            base_url=base_url,
            client_id=client_id,
            request_timeout_s=request_timeout_s,
        )
        comfy_ws_wait_prompt_done(
            ws=ws,
            prompt_id=prompt_id,
            request_timeout_s=request_timeout_s,
            job_timeout_s=job_timeout_s,
        )
        return
    except ComfyUIClientError as exc:
        if exc.code not in {"ws_connect_failed", "ws_receive_failed"}:
            raise
        LOG.warning(
            "ComfyUI WS fallback to history: prompt_id=%s ws_error_code=%s",
            prompt_id,
            exc.code,
        )
    finally:
        if ws is not None:
            close_method = getattr(ws, "close", None)
            if callable(close_method):
                _ = close_method()

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
                    "wait_mode": "history_poll",
                },
            )

        history_item = comfy_get_history_item(
            base_url=base_url,
            prompt_id=prompt_id,
            request_timeout_s=request_timeout_s,
        )
        if _history_has_images(history_item):
            return

        remaining_s = job_timeout_s - (time.monotonic() - started_at)
        if remaining_s <= 0:
            continue
        time.sleep(min(HISTORY_FALLBACK_POLL_INTERVAL_S, remaining_s))


def comfy_get_history_item(
    base_url: str,
    prompt_id: str,
    request_timeout_s: float = 30.0,
) -> dict[str, object]:
    url = _build_http_url(base_url, f"history/{prompt_id}")
    on_retry, on_giveup = _build_get_retry_callbacks(default_url=url)
    response = retry_call(
        lambda: _request_history_item_with_transient_mapping(
            url=url,
            request_timeout_s=request_timeout_s,
        ),
        retry_exceptions=(ComfyUITransientRequestError,),
        max_attempts=HISTORY_GET_RETRY_MAX_ATTEMPTS,
        stop_after_delay_s=HISTORY_GET_RETRY_STOP_AFTER_DELAY_S,
        on_retry=on_retry,
        on_giveup=on_giveup,
    )
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
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    url = _build_http_url(base_url, "view")
    params = comfy_build_view_params(image)
    on_retry, on_giveup = _build_get_retry_callbacks(default_url=url)
    return retry_call(
        lambda: _download_view_image_once(
            url=url,
            params=params,
            request_timeout_s=request_timeout_s,
            output_path=path,
        ),
        retry_exceptions=(ComfyUITransientRequestError,),
        max_attempts=VIEW_GET_RETRY_MAX_ATTEMPTS,
        stop_after_delay_s=VIEW_GET_RETRY_STOP_AFTER_DELAY_S,
        on_retry=on_retry,
        on_giveup=on_giveup,
    )


def _build_get_retry_callbacks(
    *,
    default_url: str,
) -> tuple[Callable[[int, float, Exception], None], Callable[[int, Exception], None]]:
    def on_retry(attempts: int, wait_s: float, exc: Exception) -> None:
        method, url, status_code = _extract_request_log_fields(
            exc,
            default_method="GET",
            default_url=default_url,
        )
        LOG.warning(
            "ComfyUI request retry: attempts=%d wait_s=%.3f method=%s url=%s status_code=%s",
            attempts,
            wait_s,
            method,
            url,
            status_code,
        )

    def on_giveup(attempts: int, exc: Exception) -> None:
        method, url, status_code = _extract_request_log_fields(
            exc,
            default_method="GET",
            default_url=default_url,
        )
        LOG.warning(
            "ComfyUI request give up: attempts=%d method=%s url=%s status_code=%s",
            attempts,
            method,
            url,
            status_code,
        )

    return on_retry, on_giveup


def _extract_request_log_fields(
    exc: Exception,
    *,
    default_method: str,
    default_url: str,
) -> tuple[str, str, int | None]:
    method = default_method
    url = default_url
    status_code: int | None = None

    if isinstance(exc, ComfyUIClientError):
        method_obj = exc.context.get("method")
        if isinstance(method_obj, str) and method_obj:
            method = method_obj

        url_obj = exc.context.get("url")
        if isinstance(url_obj, str) and url_obj:
            url = url_obj

        status_code_obj = exc.context.get("status_code")
        if isinstance(status_code_obj, int) and not isinstance(status_code_obj, bool):
            status_code = status_code_obj

    return method, url, status_code


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


def _request_history_item_with_transient_mapping(
    *,
    url: str,
    request_timeout_s: float,
) -> requests.Response:
    method = "GET"
    try:
        response = requests.get(url, timeout=request_timeout_s, params=None)
        response.raise_for_status()
        return response
    except requests.HTTPError as exc:
        status_code = _extract_status_code(exc)
        context = _build_http_error_context(
            method=method, url=url, status_code=status_code
        )
        if _is_transient_http_status_code(status_code):
            raise ComfyUITransientRequestError(
                "http request failed",
                code="http_request_failed",
                context=context,
            ) from exc
        raise ComfyUIRequestError(
            "http request failed",
            code="http_request_failed",
            context=context,
        ) from exc
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise ComfyUITransientRequestError(
            "http request failed",
            code="http_request_failed",
            context={"method": method, "url": url},
        ) from exc
    except requests.RequestException as exc:
        status_code = _extract_status_code(exc)
        context = _build_http_error_context(
            method=method, url=url, status_code=status_code
        )
        raise ComfyUIRequestError(
            "http request failed",
            code="http_request_failed",
            context=context,
        ) from exc


def _request_view_with_transient_mapping(
    *,
    url: str,
    params: dict[str, str],
    request_timeout_s: float,
    stream: bool,
) -> requests.Response:
    method = "GET"
    try:
        response = requests.get(
            url,
            timeout=request_timeout_s,
            params=params,
            stream=stream,
        )
        response.raise_for_status()
        return response
    except requests.HTTPError as exc:
        status_code = _extract_status_code(exc)
        context = _build_http_error_context(
            method=method,
            url=url,
            status_code=status_code,
        )
        if _is_transient_view_status_code(status_code):
            raise ComfyUITransientRequestError(
                "http request failed",
                code="http_request_failed",
                context=context,
            ) from exc
        raise ComfyUIRequestError(
            "http request failed",
            code="http_request_failed",
            context=context,
        ) from exc
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise ComfyUITransientRequestError(
            "http request failed",
            code="http_request_failed",
            context={"method": method, "url": url},
        ) from exc
    except requests.RequestException as exc:
        status_code = _extract_status_code(exc)
        context = _build_http_error_context(
            method=method,
            url=url,
            status_code=status_code,
        )
        raise ComfyUIRequestError(
            "http request failed",
            code="http_request_failed",
            context=context,
        ) from exc


def _download_view_image_once(
    *,
    url: str,
    params: dict[str, str],
    request_timeout_s: float,
    output_path: Path,
) -> Path:
    response = _request_view_with_transient_mapping(
        url=url,
        params=params,
        request_timeout_s=request_timeout_s,
        stream=True,
    )
    temp_path: Path | None = None
    replaced = False
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(output_path.parent),
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            for chunk in cast(Iterator[bytes], response.iter_content(chunk_size=8192)):
                if chunk:
                    _ = temp_file.write(chunk)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, output_path)
        replaced = True
        return output_path
    except requests.RequestException as exc:
        context = _build_http_error_context(
            method="GET",
            url=url,
            status_code=getattr(response, "status_code", None),
        )
        if isinstance(
            exc,
            (
                requests.ConnectionError,
                requests.Timeout,
                requests.exceptions.ChunkedEncodingError,
            ),
        ):
            raise ComfyUITransientRequestError(
                "http request failed",
                code="http_request_failed",
                context=context,
            ) from exc
        raise ComfyUIRequestError(
            "http request failed",
            code="http_request_failed",
            context=context,
        ) from exc
    finally:
        close_method = getattr(response, "close", None)
        if callable(close_method):
            _ = close_method()
        if temp_path is not None and not replaced and temp_path.exists():
            temp_path.unlink()


def _extract_status_code(exc: requests.RequestException) -> int | None:
    response = exc.response
    if response is None:
        return None

    status_code_obj = getattr(response, "status_code", None)
    if isinstance(status_code_obj, int):
        return status_code_obj
    return None


def _build_http_error_context(
    *,
    method: str,
    url: str,
    status_code: int | None,
) -> dict[str, object]:
    context: dict[str, object] = {"method": method, "url": url}
    if status_code is not None:
        context["status_code"] = status_code
    return context


def _is_transient_http_status_code(status_code: int | None) -> bool:
    if status_code is None:
        return False
    if status_code in _HISTORY_GET_RETRYABLE_STATUSES:
        return True
    return 500 <= status_code <= 599


def _is_transient_view_status_code(status_code: int | None) -> bool:
    if status_code is None:
        return False
    if status_code == 404:
        return True
    return status_code in _VIEW_GET_RETRYABLE_STATUSES


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


def _history_has_images(history_item: dict[str, object]) -> bool:
    outputs_obj = history_item.get("outputs")
    if not isinstance(outputs_obj, dict):
        return False

    outputs = cast(dict[str, object], outputs_obj)
    for output_obj in outputs.values():
        if not isinstance(output_obj, dict):
            continue
        output = cast(dict[str, object], output_obj)
        images_obj = output.get("images")
        if isinstance(images_obj, list) and len(cast(list[object], images_obj)) > 0:
            return True
    return False


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


def _raise_if_terminal_error(message: dict[str, object], prompt_id: str) -> None:
    message_type_obj = message.get("type")
    if message_type_obj not in {"execution_error", "execution_interrupted"}:
        return

    data_obj = message.get("data")
    if not isinstance(data_obj, dict):
        return
    data = cast(dict[str, object], data_obj)

    message_prompt_id = data.get("prompt_id")
    if not isinstance(message_prompt_id, str) or message_prompt_id != prompt_id:
        return

    message_type = cast(str, message_type_obj)
    context: dict[str, object] = {"prompt_id": prompt_id}
    for key in ("node_id", "node_type", "exception_type", "exception_message"):
        value = _compact_context_value(data.get(key))
        if value is not None:
            context[key] = value

    detail = context.get("exception_message")
    if isinstance(detail, str) and detail:
        message_text = f"prompt {prompt_id} {message_type}: {detail}"
    else:
        message_text = f"prompt {prompt_id} {message_type}"

    raise ComfyUIClientError(
        message_text,
        code=message_type,
        context=context,
    )


def _compact_context_value(value: object, max_length: int = 200) -> object | None:
    if value is None:
        return None

    if isinstance(value, bool | int | float):
        return value

    if isinstance(value, str):
        if len(value) <= max_length:
            return value
        return f"{value[:max_length]}...(truncated)"

    text = repr(value)
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}...(truncated)"
