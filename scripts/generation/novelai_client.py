from __future__ import annotations

import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Any

from novelai import NovelAI
from novelai.exceptions import (
    AuthenticationError,
    NetworkError,
    NovelAIError,
    RateLimitError,
    ServerError,
)
from novelai.types import GenerateImageParams

LOG = logging.getLogger(__name__)

_NOVELAI_SAMPLER_NAMES = {
    "euler",
    "euler_ancestral",
    "k_euler",
    "k_euler_ancestral",
    "k_dpm_2",
    "k_dpm_2_ancestral",
    "k_dpmpp_2m",
    "k_dpmpp_2s_ancestral",
    "k_dpmpp_sde",
    "ddim",
}

_NOVELAI_MODEL_NAMES = {
    "nai-diffusion-4-5-full",
    "nai-diffusion-4-5-curated",
    "nai-diffusion-4-full",
    "nai-diffusion-4-curated",
    "nai-diffusion-3",
    "nai-diffusion-3-furry",
    "nai-diffusion-5-full",
    "nai-diffusion-5-curated",
}

# V5 代际模型：Opus 订阅的免费生图额度改为可耗尽的"电池"政策，
# 耗尽后请求不报错、静默转 Anlas 计费，因此生成前必须轮询电量。
_V5_MODEL_NAMES = frozenset(
    {
        "nai-diffusion-5-full",
        "nai-diffusion-5-curated",
    }
)

# Anlas 守卫错误码：写入 metadata.jsonl 的 error.code，
# 供 --retry-error-code 精准捞回硬停的网格单元。
# 历史 run 里的 anlas_billing_detected / anlas_balance_unverifiable
# 记录仍按原码捞回；余额核对相关决策见 docs/adr/0002。
_GUARD_CODE_PARAM_VIOLATION = "anlas_param_violation"
_GUARD_CODE_BATTERY_LOW = "anlas_battery_low"

# Opus 订阅免费资格参数上限（超出即可能转 Anlas 计费）。
_FREE_TIER_MAX_AREA_PX = 1024 * 1024
_FREE_TIER_MAX_STEPS = 28
_OPUS_TIER = 3

_WEIGHTED_TAG_RE = re.compile(r"\(([^)]+)\)")


def _convert_prompt_to_novelai_format(prompt: str | None) -> str:
    """
    Convert ComfyUI/WebUI (tag:weight) format to NovelAI weight::tag :: format.
    Called just before API submission. Metadata should keep the original format.
    """
    if not prompt:
        return prompt or ""

    def _replace(match: re.Match[str]) -> str:
        inner = match.group(1)
        # Scan from right to find the colon that separates tag from weight.
        # This correctly handles tags that contain colons, e.g. (artist:name:1.1).
        for colon_pos in range(len(inner) - 1, -1, -1):
            if inner[colon_pos] == ":":
                tag = inner[:colon_pos].strip()
                weight_str = inner[colon_pos + 1 :].strip()
                try:
                    weight = float(weight_str)
                except ValueError:
                    continue
                if abs(weight - 1.0) < 1e-9:
                    return tag
                weight_clean = weight_str.rstrip("0").rstrip(".")
                return f"{weight_clean}::{tag} ::"
        # No valid weight found; preserve the original token unchanged.
        return match.group(0)

    return _WEIGHTED_TAG_RE.sub(_replace, prompt)


_ENV_API_KEY = "NOVELAI_API_KEY"
_ENV_MIN_INTERVAL = "NOVELAI_MIN_INTERVAL_S"
_ENV_MAX_RETRIES = "NOVELAI_MAX_RETRIES"
_ENV_REQUEST_TIMEOUT = "NOVELAI_REQUEST_TIMEOUT_S"
_ENV_INTERVAL_JITTER = "NOVELAI_INTERVAL_JITTER_S"
_ENV_RATE_LIMIT_COOLDOWN = "NOVELAI_RATE_LIMIT_COOLDOWN_S"
_ENV_RATE_LIMIT_JITTER = "NOVELAI_RATE_LIMIT_JITTER_S"
_ENV_BATTERY_MIN_PERCENT = "NOVELAI_BATTERY_MIN_PERCENT"

_DEFAULT_MIN_INTERVAL = 5.0
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_REQUEST_TIMEOUT = 120.0
_DEFAULT_INTERVAL_JITTER = 0.0
_DEFAULT_RATE_LIMIT_COOLDOWN = 30.0
_DEFAULT_RATE_LIMIT_JITTER = 0.0
_DEFAULT_BATTERY_MIN_PERCENT = 5.0


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw:
        try:
            return float(raw.strip())
        except ValueError:
            pass
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw:
        try:
            return int(raw.strip())
        except ValueError:
            pass
    return default


class NovelAIAnlasGuardError(Exception):
    """Anlas 守卫触发：拒绝发起不满足免费资格的请求，或请求电量耗尽中止运行。

    实现 as_metadata() 契约（type/code/message），经错误序列化写入
    metadata.jsonl 的 error 字段；code 为守卫专属错误码，
    供 --retry-error-code 精准恢复硬停的网格单元。
    """

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
            "type": "anlas_guard",
            "code": self.code,
            "message": str(self),
            "context": self.context,
        }


class NovelAIAPIClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        min_interval_s: float | None = None,
        max_retries: int | None = None,
        request_timeout_s: float | None = None,
        interval_jitter_s: float | None = None,
        rate_limit_cooldown_s: float | None = None,
        rate_limit_jitter_s: float | None = None,
        battery_min_percent: float | None = None,
    ) -> None:
        self._api_key = api_key or _resolve_api_key()
        self._min_interval = (
            min_interval_s
            if min_interval_s is not None
            else _env_float(_ENV_MIN_INTERVAL, _DEFAULT_MIN_INTERVAL)
        )
        self._max_retries = (
            max_retries
            if max_retries is not None
            else _env_int(_ENV_MAX_RETRIES, _DEFAULT_MAX_RETRIES)
        )
        self._request_timeout = (
            request_timeout_s
            if request_timeout_s is not None
            else _env_float(_ENV_REQUEST_TIMEOUT, _DEFAULT_REQUEST_TIMEOUT)
        )
        self._jitter = (
            interval_jitter_s
            if interval_jitter_s is not None
            else _env_float(_ENV_INTERVAL_JITTER, _DEFAULT_INTERVAL_JITTER)
        )
        self._rate_limit_cooldown = (
            rate_limit_cooldown_s
            if rate_limit_cooldown_s is not None
            else _env_float(_ENV_RATE_LIMIT_COOLDOWN, _DEFAULT_RATE_LIMIT_COOLDOWN)
        )
        self._rate_limit_jitter = (
            rate_limit_jitter_s
            if rate_limit_jitter_s is not None
            else _env_float(_ENV_RATE_LIMIT_JITTER, _DEFAULT_RATE_LIMIT_JITTER)
        )
        self._battery_min_percent = (
            battery_min_percent
            if battery_min_percent is not None
            else _env_float(_ENV_BATTERY_MIN_PERCENT, _DEFAULT_BATTERY_MIN_PERCENT)
        )
        self._sdk = NovelAI(
            api_key=self._api_key or "dry-run",
            timeout=self._request_timeout,
        )

    def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str | None,
        model: str,
        width: int,
        height: int,
        steps: int,
        scale: float,
        sampler: str,
        seed: int,
        n_samples: int,
    ) -> list[Any]:
        model = _normalize_model(model)
        size = (width, height)
        sampler = _normalize_sampler(sampler)

        # Anlas 守卫第一层：免费资格参数前置拦截，不合规直接拒绝、不发起请求。
        _validate_free_tier_params(
            width=width,
            height=height,
            steps=steps,
            n_samples=n_samples,
        )

        # Anlas 守卫第二层：V5 生成前电量检查。
        if model in _V5_MODEL_NAMES:
            subscription = self._fetch_subscription()
            self._raise_if_battery_low(subscription)

        params = GenerateImageParams(
            prompt=prompt,
            negative_prompt=negative_prompt,
            model=model,
            size=size,
            steps=steps,
            scale=scale,
            sampler=sampler,
            seed=seed,
            n_samples=n_samples,
            # 质量词与 UC 预设改由 config.yaml 全量提供（quality_prompt /
            # negative_prompt），关闭 SDK 注入以保证「配置即发送」。
            # 注意：SDK 0.12.0 的 bug——用户级 "none" 会映射为 ucPreset=4，
            # 但底层请求模型限制 le=3，直接传 "none" 必然 ValidationError；
            # 因此用 "light" 占位并传 qualityToggle=False，服务端以开关
            # 为准不追加任何预设文本，负面内容完全由我们传入的字符串决定。
            quality=False,
            uc_preset="light",
        )

        # 免费资格要求纯 t2i；i2i/inpaint 等任何图像条件输入都会转计费。
        _ensure_pure_text_to_image(params)

        images = self._generate_with_retries(params)

        wait_s = max(0.0, self._min_interval + random.uniform(-self._jitter, self._jitter))
        if wait_s > 0:
            LOG.info("NovelAI 速率限制：等待 %.1f 秒", wait_s)
            time.sleep(wait_s)
        return images

    def _generate_with_retries(self, params: Any) -> list[Any]:
        max_delay = 120.0

        for attempt in range(self._max_retries + 1):
            try:
                return self._sdk.image.generate(params)
            except AuthenticationError:
                # SDK 把 401（key 无效）与 402（余额/订阅不足）都映射为
                # AuthenticationError：两者都是终态错误，402 更是首图即扣费
                # 后的信号。此子句必须先于下方 NovelAIError 兜底子句，
                # 否则认证错误会被当作可重试错误空转三次指数退避。
                raise
            except RateLimitError:
                if attempt >= self._max_retries:
                    raise
                delay = max(0.0, self._rate_limit_cooldown + random.uniform(-self._rate_limit_jitter, self._rate_limit_jitter))
                LOG.warning(
                    "NovelAI 速率限制 (429)，第 %s 次重试，等待 %.1f 秒",
                    attempt + 1,
                    delay,
                )
                time.sleep(delay)
                continue
            except NetworkError:
                if attempt >= self._max_retries:
                    raise
                delay = min(max_delay, 10.0 * (2**attempt) + random.uniform(0, 3))
                LOG.warning(
                    "NovelAI 网络错误，第 %s 次重试，等待 %.1f 秒",
                    attempt + 1,
                    delay,
                )
                time.sleep(delay)
                continue
            except (ServerError, NovelAIError):
                if attempt >= self._max_retries:
                    raise
                delay = min(max_delay, 10.0 * (2**attempt) + random.uniform(0, 3))
                LOG.warning(
                    "NovelAI 服务端错误，第 %s 次重试，等待 %.1f 秒",
                    attempt + 1,
                    delay,
                )
                time.sleep(delay)
                continue

        raise RuntimeError("unreachable: max retries exceeded")

    def preflight(self, *, model: str | None = None) -> None:
        """启动预检：确认 Opus 订阅；model 为 V5 时顺带检查电池电量。

        非 Opus（tier != 3）订阅不存在免费生图档，任何请求都可能计费，
        直接中止运行。V5 电量耗尽（含 retry 运行）同样中止，
        等待电量回充后由人工择机重跑。
        """
        subscription = self._fetch_subscription()
        tier = getattr(subscription, "tier", None)
        if tier != _OPUS_TIER:
            raise RuntimeError(
                f"Anlas 守卫预检失败：API key 非 Opus 订阅（tier={tier}），"
                "免费生图档不存在，已中止运行"
            )
        if model is not None and model in _V5_MODEL_NAMES:
            self._raise_if_battery_low(subscription)
        LOG.info("Anlas 守卫预检通过：Opus 订阅")

    def _fetch_subscription(self) -> Any:
        """查询订阅接口（GET /user/subscription）。测试经 monkeypatch 此方法打桩。"""
        return self._sdk.user.get_subscription()

    def _raise_if_battery_low(self, subscription: Any) -> None:
        usage_percent = _extract_usage_percent(subscription)
        is_negative = _extract_usage_is_negative(subscription)
        context: dict[str, object] = {
            "threshold_percent": self._battery_min_percent,
            "usage_percent": usage_percent,
            "is_negative": is_negative,
        }
        if is_negative is True:
            raise NovelAIAnlasGuardError(
                "V5 电量已耗尽（usage.isNegative=true），继续生成将转 Anlas 计费",
                code=_GUARD_CODE_BATTERY_LOW,
                context=context,
            )
        if usage_percent is None:
            # 电量不可读时按耗尽处理：宁可硬停也不冒静默计费的风险。
            raise NovelAIAnlasGuardError(
                "V5 电量不可读：订阅接口未返回有效 usage.percent，按耗尽处理",
                code=_GUARD_CODE_BATTERY_LOW,
                context=context,
            )
        if usage_percent < self._battery_min_percent:
            raise NovelAIAnlasGuardError(
                f"V5 电量不足：usage.percent={usage_percent} "
                f"低于阈值 {self._battery_min_percent}",
                code=_GUARD_CODE_BATTERY_LOW,
                context=context,
            )

    def has_key(self) -> bool:
        return self._api_key is not None


def _resolve_api_key() -> str | None:
    raw = os.getenv(_ENV_API_KEY)
    if raw is None:
        return None
    value = raw.strip()
    return value if value else None


def _normalize_sampler(sampler: str | None) -> str:
    if sampler is None:
        return "k_euler_ancestral"
    normalized = sampler.strip().lower()
    if normalized in _NOVELAI_SAMPLER_NAMES:
        return normalized
    candidate = f"k_{normalized}"
    if candidate in _NOVELAI_SAMPLER_NAMES:
        return candidate
    LOG.info("未知采样器 %s，回退到 k_euler_ancestral", sampler)
    return "k_euler_ancestral"


def _normalize_model(raw_model: str | None) -> str:
    if raw_model is None:
        return "nai-diffusion-4-5-full"
    normalized = raw_model.strip().lower()
    if normalized in _NOVELAI_MODEL_NAMES:
        return normalized
    models = ", ".join(sorted(_NOVELAI_MODEL_NAMES))
    raise ValueError(f"未知 NovelAI 模型: {raw_model}; 可选: {models}")


def _validate_free_tier_params(
    *,
    width: int,
    height: int,
    steps: int,
    n_samples: int,
) -> None:
    """免费资格参数前置拦截：不满足 Opus 免费生图条件时拒绝发起请求。"""
    area = width * height
    if area > _FREE_TIER_MAX_AREA_PX:
        raise NovelAIAnlasGuardError(
            f"免费资格参数不合规：面积 {width}x{height}={area}px "
            f"超过 {_FREE_TIER_MAX_AREA_PX}px 上限",
            code=_GUARD_CODE_PARAM_VIOLATION,
            context={
                "param": "area",
                "width": width,
                "height": height,
                "area": area,
                "limit": _FREE_TIER_MAX_AREA_PX,
            },
        )
    if steps > _FREE_TIER_MAX_STEPS:
        raise NovelAIAnlasGuardError(
            f"免费资格参数不合规：steps={steps} 超过免费上限 {_FREE_TIER_MAX_STEPS}",
            code=_GUARD_CODE_PARAM_VIOLATION,
            context={"param": "steps", "steps": steps, "limit": _FREE_TIER_MAX_STEPS},
        )
    if n_samples != 1:
        raise NovelAIAnlasGuardError(
            f"免费资格参数不合规：n_samples={n_samples}，仅支持单张生成",
            code=_GUARD_CODE_PARAM_VIOLATION,
            context={"param": "n_samples", "n_samples": n_samples, "limit": 1},
        )


_I2I_PARAM_FIELDS = ("i2i", "inpaint", "controlnet", "character_references")


def _ensure_pure_text_to_image(params: Any) -> None:
    """纯 t2i 校验：任何图像条件输入（i2i/inpaint 等）都会转 Anlas 计费。"""
    for field in _I2I_PARAM_FIELDS:
        if getattr(params, field, None) is not None:
            raise NovelAIAnlasGuardError(
                f"免费资格参数不合规：检测到非纯 t2i 参数 {field}",
                code=_GUARD_CODE_PARAM_VIOLATION,
                context={"param": field},
            )


def _extract_usage_value(subscription: Any, key: str) -> Any:
    usage = getattr(subscription, "usage", None)
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage.get(key)
    return getattr(usage, key, None)


def _extract_usage_percent(subscription: Any) -> float | None:
    raw = _extract_usage_value(subscription, "percent")
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    return float(raw)


def _extract_usage_is_negative(subscription: Any) -> bool | None:
    raw = _extract_usage_value(subscription, "isNegative")
    if not isinstance(raw, bool):
        return None
    return raw


def _build_error_payload(exc: Exception) -> dict[str, object]:
    # 守卫异常实现 as_metadata() 契约，专属错误码经此进入 metadata.jsonl。
    as_metadata = getattr(exc, "as_metadata", None)
    if callable(as_metadata):
        payload = as_metadata()
        if isinstance(payload, dict):
            return payload
    if isinstance(exc, RateLimitError):
        error_type = "rate_limited"
    elif isinstance(exc, NetworkError):
        error_type = "network_error"
    elif isinstance(exc, AuthenticationError):
        error_type = "auth_error"
    elif isinstance(exc, (ServerError, NovelAIError)):
        error_type = "api_error"
    else:
        error_type = "unknown_error"
    return {"type": error_type, "message": str(exc)}


def novelai_worker(
    client: NovelAIAPIClient,
    model: str,
) -> Any:
    from scripts.generation.runner_coordinator import _GenOutcome, _serialize_error

    LOG = logging.getLogger(__name__)

    def _worker(
        args: Any,
        run_dir: Any,
        workflow_context: Any,
        plan: Any,
        patch_workflow: Any,
        workflow_overrides_factory: Any,
        final_negative_prompt_for_x_row: Any,
        submit_prompt: Any,
        wait_prompt_done_with_fallback: Any,
        build_base_metadata_record: Any,
        now_iso: Any,
    ) -> Any:
        _ = (workflow_context, patch_workflow, workflow_overrides_factory)
        _ = (submit_prompt, wait_prompt_done_with_fallback)

        started_at = now_iso()
        started_mono = time.monotonic()

        try:
            negative_prompt = final_negative_prompt_for_x_row(
                args, None, plan.x_row
            )
            if negative_prompt is None:
                negative_prompt = ""

            converted_positive = _convert_prompt_to_novelai_format(
                plan.positive_prompt
            )
            converted_negative = _convert_prompt_to_novelai_format(
                negative_prompt
            )

            width = getattr(args, "width", 832) or 832
            height = getattr(args, "height", 1216) or 1216
            steps = getattr(args, "steps", 28) or 28
            scale = getattr(args, "cfg", 5.0) or 5.0
            sampler = getattr(args, "sampler_name", None)
            n_samples = getattr(args, "batch_size", 1) or 1

            images = client.generate(
                prompt=converted_positive,
                negative_prompt=converted_negative if converted_negative else None,
                model=model,
                width=width,
                height=height,
                steps=steps,
                scale=scale,
                sampler=sampler,
                seed=plan.seed,
                n_samples=n_samples,
            )

            local_paths: list[str] = []
            for i, img in enumerate(images):
                if i == 0:
                    local_path = f"images/x{plan.x_index}-y{plan.y_index}.png"
                else:
                    local_path = f"images/x{plan.x_index}-y{plan.y_index}-{i}.png"
                save_path = run_dir / local_path
                save_path.parent.mkdir(parents=True, exist_ok=True)
                img.save(str(save_path), format="PNG")
                local_paths.append(local_path)

            finished_at = now_iso()
            elapsed_ms = int((time.monotonic() - started_mono) * 1000)
            record = build_base_metadata_record(
                status="success",
                x_index=plan.x_index,
                y_index=plan.y_index,
                x_row=plan.x_row,
                y_value=plan.y_value,
                positive_prompt=plan.positive_prompt,
                prompt_hash=plan.prompt_hash,
                seed=plan.seed,
                generation_params=plan.generation_params,
                workflow_hash=plan.workflow_hash,
                attempt=plan.attempt,
            )
            record["x_description"] = plan.x_description
            _apply_plan_y_prompt_ref(record, plan)
            record["local_image_paths"] = local_paths
            record["local_image_path"] = local_paths[0] if local_paths else None
            record["started_at"] = started_at
            record["finished_at"] = finished_at
            record["elapsed_ms"] = elapsed_ms

            return _GenOutcome(record=record, download=None)

        except Exception as exc:
            LOG.exception("NovelAI 生成失败: x=%s y=%s", plan.x_index, plan.y_index)
            finished_at = now_iso()
            elapsed_ms = int((time.monotonic() - started_mono) * 1000)
            record = build_base_metadata_record(
                status="failed",
                x_index=plan.x_index,
                y_index=plan.y_index,
                x_row=plan.x_row,
                y_value=plan.y_value,
                positive_prompt=plan.positive_prompt,
                prompt_hash=plan.prompt_hash,
                seed=plan.seed,
                generation_params=plan.generation_params,
                workflow_hash=plan.workflow_hash,
                attempt=plan.attempt,
            )
            record["x_description"] = plan.x_description
            _apply_plan_y_prompt_ref(record, plan)
            record["started_at"] = started_at
            record["finished_at"] = finished_at
            record["elapsed_ms"] = elapsed_ms
            record["error"] = _build_error_payload(exc)
            # V5 电量耗尽是运行级硬停信号：除记录失败外，还要求协调器
            # 停止提交剩余网格单元；参数不合规等逐格错误不置位。
            abort = (
                isinstance(exc, NovelAIAnlasGuardError)
                and exc.code == _GUARD_CODE_BATTERY_LOW
            )
            return _GenOutcome(record=record, download=None, abort=abort)

    return _worker


def _apply_plan_y_prompt_ref(record: dict[str, object], plan: Any) -> None:
    y_prompt_ref = getattr(plan, "y_prompt_ref", None)
    if not isinstance(y_prompt_ref, dict):
        return
    style_key = y_prompt_ref.get("style_key")
    collection_id = y_prompt_ref.get("collection_id")
    item_index = y_prompt_ref.get("item_index")
    if isinstance(style_key, str) and style_key:
        record["y_style_key"] = style_key
    if isinstance(collection_id, str) and collection_id:
        record["y_collection_id"] = collection_id
    if isinstance(item_index, int) and not isinstance(item_index, bool):
        record["y_item_index"] = item_index


__all__ = [
    "NovelAIAPIClient",
    "NovelAIAnlasGuardError",
    "_build_error_payload",
    "_normalize_model",
    "novelai_worker",
    "_env_float",
    "_env_int",
]
