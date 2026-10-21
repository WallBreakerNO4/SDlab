# pyright: basic, reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelai.exceptions import (
    AuthenticationError,
    NetworkError,
    RateLimitError,
)
from novelai.types import Subscription

from scripts.generation import novelai_client
from scripts.generation.novelai_client import (
    _GUARD_CODE_BATTERY_LOW,
    _GUARD_CODE_PARAM_VIOLATION,
    NovelAIAnlasGuardError,
)


# --- Fake SDK 与客户端工厂 ---


class _FakeImageAPI:
    def __init__(
        self,
        *,
        images: list[object] | None = None,
        errors: list[Exception] | None = None,
    ) -> None:
        self.calls: list[object] = []
        self._images = images if images is not None else []
        self._errors = list(errors or [])

    def generate(self, params: object) -> list[object]:
        self.calls.append(params)
        if self._errors:
            raise self._errors.pop(0)
        return list(self._images)


class _FakeUserAPI:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def get_subscription(self) -> object:
        self.calls += 1
        if not self.responses:
            raise AssertionError("意外的订阅查询：响应队列已空")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _subscription(
    *,
    tier: int = 3,
    usage: object = None,
) -> argparse.Namespace:
    return argparse.Namespace(tier=tier, usage=usage)


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    image_api: _FakeImageAPI,
    user_api: _FakeUserAPI,
    battery_min_percent: float | None = 5.0,
    battery_poll_interval_s: float | None = None,
    battery_wait_timeout_s: float | None = None,
    battery_hard_stop: bool = False,
) -> novelai_client.NovelAIAPIClient:
    captured: dict[str, object] = {}

    def _factory(**kwargs: object) -> argparse.Namespace:
        captured.update(kwargs)
        return argparse.Namespace(user=user_api, image=image_api)

    monkeypatch.setattr(novelai_client, "NovelAI", _factory)

    kwargs: dict[str, object] = {
        "api_key": "test-key",
        "min_interval_s": 0.0,
        # 先跑过的 main() 测试会经 _autoload_dotenv 把真实 .env 灌进进程环境，
        # 这里显式钉死抖动，避免成功 generate 后的 min_interval 睡眠随机化时钟断言。
        "interval_jitter_s": 0.0,
        "battery_hard_stop": battery_hard_stop,
    }
    # battery_min_percent=None 表示走环境变量/默认值路径，供阈值环境变量测试使用。
    if battery_min_percent is not None:
        kwargs["battery_min_percent"] = battery_min_percent
    if battery_poll_interval_s is not None:
        kwargs["battery_poll_interval_s"] = battery_poll_interval_s
    if battery_wait_timeout_s is not None:
        kwargs["battery_wait_timeout_s"] = battery_wait_timeout_s
    return novelai_client.NovelAIAPIClient(**kwargs)  # type: ignore[arg-type]


class _FakeClock:
    """替代 novelai_client.time：可控单调时钟 + 睡眠记录，测试零真实等待。"""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _wait_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    image_api: _FakeImageAPI,
    clock: _FakeClock,
    responses: list[object],
    battery_wait_timeout_s: float | None = None,
    battery_poll_interval_s: float | None = 300.0,
) -> novelai_client.NovelAIAPIClient:
    # 等待循环的睡眠/超时全部走可控假时钟。
    monkeypatch.setattr(novelai_client, "time", clock)
    return _make_client(
        monkeypatch,
        image_api=image_api,
        user_api=_FakeUserAPI(responses),
        battery_wait_timeout_s=battery_wait_timeout_s,
        battery_poll_interval_s=battery_poll_interval_s,
    )


def _generate_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "prompt": "1girl, masterpiece,",
        "negative_prompt": None,
        "model": "nai-diffusion-4-5-full",
        "width": 832,
        "height": 1216,
        "steps": 28,
        "scale": 5.0,
        "sampler": "k_euler_ancestral",
        "seed": 123,
        "n_samples": 1,
    }
    kwargs.update(overrides)
    return kwargs


# --- 模型白名单 ---


def test_normalize_model_accepts_v5_keys() -> None:
    assert (
        novelai_client._normalize_model("nai-diffusion-5-full")
        == "nai-diffusion-5-full"
    )
    assert (
        novelai_client._normalize_model("nai-diffusion-5-curated")
        == "nai-diffusion-5-curated"
    )


def test_normalize_model_still_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="未知 NovelAI 模型"):
        novelai_client._normalize_model("nai-diffusion-6-preview")


# --- 免费资格参数前置拦截 ---


@pytest.mark.parametrize(
    ("overrides", "param"),
    [
        pytest.param({"width": 1216, "height": 1216}, "area", id="area_over_limit"),
        pytest.param({"steps": 29}, "steps", id="steps_over_limit"),
        pytest.param({"n_samples": 2}, "n_samples", id="batch_over_one"),
    ],
)
def test_generate_rejects_non_free_tier_params_before_request(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    param: str,
) -> None:
    image_api = _FakeImageAPI(images=[object()])
    user_api = _FakeUserAPI([])
    client = _make_client(monkeypatch, image_api=image_api, user_api=user_api)

    with pytest.raises(NovelAIAnlasGuardError) as exc_info:
        client.generate(**_generate_kwargs(**overrides))  # type: ignore[arg-type]

    metadata = exc_info.value.as_metadata()
    assert exc_info.value.code == _GUARD_CODE_PARAM_VIOLATION
    assert metadata["type"] == "anlas_guard"
    assert metadata["code"] == _GUARD_CODE_PARAM_VIOLATION
    assert isinstance(metadata["message"], str)
    # 参数守卫是纯本地校验：请求未发出，订阅查询也不应发生。
    assert image_api.calls == []
    assert user_api.calls == 0
    assert exc_info.value.context["param"] == param


def test_free_tier_param_boundary_values_pass_validation() -> None:
    novelai_client._validate_free_tier_params(
        width=1024, height=1024, steps=28, n_samples=1
    )


def test_pure_t2i_guard_rejects_image_conditioned_params() -> None:
    i2i_params = argparse.Namespace(
        i2i=object(),
        inpaint=None,
        controlnet=None,
        character_references=None,
    )

    with pytest.raises(NovelAIAnlasGuardError) as exc_info:
        novelai_client._ensure_pure_text_to_image(i2i_params)

    assert exc_info.value.code == _GUARD_CODE_PARAM_VIOLATION
    assert exc_info.value.context["param"] == "i2i"


def test_pure_t2i_guard_allows_clean_params() -> None:
    clean_params = argparse.Namespace(
        i2i=None,
        inpaint=None,
        controlnet=None,
        character_references=None,
    )
    novelai_client._ensure_pure_text_to_image(clean_params)


# --- 合规参数照常放行 ---


def test_compliant_v45_generation_passes_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(images=["img"])
    # 仅 preflight 查一次订阅（tier 确认）；V4.5 无电池政策，生成不再查订阅。
    user_api = _FakeUserAPI([_subscription()])
    client = _make_client(monkeypatch, image_api=image_api, user_api=user_api)
    client.preflight()

    images = client.generate(**_generate_kwargs())

    assert images == ["img"]
    assert len(image_api.calls) == 1
    assert user_api.calls == 1


# --- V5 电量检查（--battery-hard-stop 旧工作模式，ADR 0002 真中止）---


def test_v5_battery_hard_stop_mode_below_threshold_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(images=[object()])
    sub = _subscription(usage={"percent": 3, "isNegative": False})
    client = _make_client(
        monkeypatch,
        image_api=image_api,
        user_api=_FakeUserAPI([sub]),
        battery_hard_stop=True,
    )

    with pytest.raises(NovelAIAnlasGuardError) as exc_info:
        client.generate(**_generate_kwargs(model="nai-diffusion-5-full"))

    assert exc_info.value.code == _GUARD_CODE_BATTERY_LOW
    assert exc_info.value.context["usage_percent"] == 3.0
    assert image_api.calls == []


def test_v5_battery_hard_stop_mode_negative_stops_even_with_high_percent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(images=[object()])
    sub = _subscription(usage={"percent": 90, "isNegative": True})
    client = _make_client(
        monkeypatch,
        image_api=image_api,
        user_api=_FakeUserAPI([sub]),
        battery_hard_stop=True,
    )

    with pytest.raises(NovelAIAnlasGuardError) as exc_info:
        client.generate(**_generate_kwargs(model="nai-diffusion-5-curated"))

    assert exc_info.value.code == _GUARD_CODE_BATTERY_LOW
    assert exc_info.value.context["is_negative"] is True
    assert image_api.calls == []


@pytest.mark.parametrize("usage", [None, {}, {"percent": "abc"}, {"isNegative": False}])
def test_v5_unreadable_battery_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    usage: object,
) -> None:
    image_api = _FakeImageAPI(images=[object()])
    sub = _subscription(usage=usage)
    client = _make_client(
        monkeypatch,
        image_api=image_api,
        user_api=_FakeUserAPI([sub]),
    )

    with pytest.raises(NovelAIAnlasGuardError) as exc_info:
        client.generate(**_generate_kwargs(model="nai-diffusion-5-full"))

    assert exc_info.value.code == _GUARD_CODE_BATTERY_LOW
    assert image_api.calls == []


def test_v45_skips_battery_check_entirely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(images=["img"])
    # V4.5 不在电池政策内：即使 usage 不可读也照常生成，且生成不再查订阅。
    user_api = _FakeUserAPI([_subscription(usage="not-a-mapping")])
    client = _make_client(monkeypatch, image_api=image_api, user_api=user_api)
    client.preflight()

    images = client.generate(**_generate_kwargs())

    assert images == ["img"]
    assert len(image_api.calls) == 1
    assert user_api.calls == 1


def test_default_battery_threshold_is_five_percent() -> None:
    assert novelai_client._DEFAULT_BATTERY_MIN_PERCENT == 5.0


def test_battery_threshold_env_var_raises_effective_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOVELAI_BATTERY_MIN_PERCENT", "80")
    image_api = _FakeImageAPI(images=[object()])
    sub = _subscription(usage={"percent": 70, "isNegative": False})
    client = _make_client(
        monkeypatch,
        image_api=image_api,
        user_api=_FakeUserAPI([sub]),
        battery_min_percent=None,
        battery_hard_stop=True,
    )

    with pytest.raises(NovelAIAnlasGuardError) as exc_info:
        client.generate(**_generate_kwargs(model="nai-diffusion-5-full"))

    assert exc_info.value.code == _GUARD_CODE_BATTERY_LOW
    assert exc_info.value.context["threshold_percent"] == 80.0


# --- V5 电量等待回充（默认模式，ADR 0003）---


def test_v5_battery_low_waits_and_resumes_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(images=["img"])
    clock = _FakeClock()
    client = _wait_client(
        monkeypatch,
        image_api=image_api,
        clock=clock,
        responses=[
            _subscription(usage={"percent": 3, "isNegative": False}),
            _subscription(usage={"percent": 4, "isNegative": False}),
            _subscription(usage={"percent": 6, "isNegative": False}),
        ],
    )

    images = client.generate(**_generate_kwargs(model="nai-diffusion-5-full"))

    assert images == ["img"]
    assert len(image_api.calls) == 1
    # 两轮轮询各睡满一个 300s 间隔（30s 分片），真实睡眠被假时钟替换。
    assert clock.now == 600.0
    assert set(clock.sleeps) == {30.0}


def test_v5_battery_wait_repeats_across_consecutive_generations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 第一格等回充后生成，消耗后再次跌破阈值 → 下一格重复等待（ADR 0003 循环语义）。
    image_api = _FakeImageAPI(images=["img1", "img2"])
    clock = _FakeClock()
    client = _wait_client(
        monkeypatch,
        image_api=image_api,
        clock=clock,
        responses=[
            _subscription(usage={"percent": 3, "isNegative": False}),
            _subscription(usage={"percent": 6, "isNegative": False}),
            _subscription(usage={"percent": 4, "isNegative": False}),
            _subscription(usage={"percent": 7, "isNegative": False}),
        ],
    )

    # _FakeImageAPI 每次调用返回全部图片；这里只关心两次生成都各自经历了一轮等待。
    assert client.generate(**_generate_kwargs(model="nai-diffusion-5-full")) == [
        "img1",
        "img2",
    ]
    assert client.generate(**_generate_kwargs(model="nai-diffusion-5-full")) == [
        "img1",
        "img2",
    ]
    assert len(image_api.calls) == 2
    assert clock.now == 600.0


def test_v5_battery_negative_waits_for_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(images=["img"])
    clock = _FakeClock()
    client = _wait_client(
        monkeypatch,
        image_api=image_api,
        clock=clock,
        responses=[
            _subscription(usage={"percent": 90, "isNegative": True}),
            _subscription(usage={"percent": 6, "isNegative": False}),
        ],
    )

    assert client.generate(**_generate_kwargs(model="nai-diffusion-5-full")) == ["img"]
    assert clock.now == 300.0


def test_v5_battery_wait_timeout_falls_back_to_hard_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(images=[object()])
    clock = _FakeClock()
    low = _subscription(usage={"percent": 3, "isNegative": False})
    client = _wait_client(
        monkeypatch,
        image_api=image_api,
        clock=clock,
        responses=[low, low, low],
        battery_wait_timeout_s=120.0,
        battery_poll_interval_s=100.0,
    )

    with pytest.raises(NovelAIAnlasGuardError) as exc_info:
        client.generate(**_generate_kwargs(model="nai-diffusion-5-full"))

    assert exc_info.value.code == _GUARD_CODE_BATTERY_LOW
    assert exc_info.value.context["wait_timeout_s"] == 120.0
    assert image_api.calls == []
    # 一轮轮询后仍未恢复，第二轮循环顶部触发超时。
    assert clock.now == 200.0


def test_v5_battery_unreadable_during_wait_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(images=[object()])
    clock = _FakeClock()
    client = _wait_client(
        monkeypatch,
        image_api=image_api,
        clock=clock,
        responses=[
            _subscription(usage={"percent": 3, "isNegative": False}),
            _subscription(usage=None),
        ],
    )

    with pytest.raises(NovelAIAnlasGuardError) as exc_info:
        client.generate(**_generate_kwargs(model="nai-diffusion-5-full"))

    assert exc_info.value.code == _GUARD_CODE_BATTERY_LOW
    assert image_api.calls == []
    # 契约变更不等待：一轮轮询发现不可读后立即硬停。
    assert clock.now == 300.0


def test_v5_battery_wait_ignores_transient_poll_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(images=["img"])
    clock = _FakeClock()
    client = _wait_client(
        monkeypatch,
        image_api=image_api,
        clock=clock,
        responses=[
            _subscription(usage={"percent": 3, "isNegative": False}),
            NetworkError("boom"),
            _subscription(usage={"percent": 6, "isNegative": False}),
        ],
    )

    assert client.generate(**_generate_kwargs(model="nai-diffusion-5-full")) == ["img"]
    # 瞬时传输错误只记日志，下一轮轮询继续。
    assert clock.now == 600.0


def test_v5_battery_wait_interrupted_by_stop_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(images=[object()])
    clock = _FakeClock()
    client = _wait_client(
        monkeypatch,
        image_api=image_api,
        clock=clock,
        responses=[_subscription(usage={"percent": 3, "isNegative": False})],
    )
    client.battery_wait_stop.set()

    with pytest.raises(NovelAIAnlasGuardError) as exc_info:
        client.generate(**_generate_kwargs(model="nai-diffusion-5-full"))

    assert exc_info.value.code == _GUARD_CODE_BATTERY_LOW
    assert exc_info.value.context["interrupted"] is True
    assert image_api.calls == []
    # 停止信号置位后等待立即放弃，不进入睡眠。
    assert clock.sleeps == []


def test_v5_battery_wait_poll_interval_sleeps_in_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(images=["img"])
    clock = _FakeClock()
    client = _wait_client(
        monkeypatch,
        image_api=image_api,
        clock=clock,
        responses=[
            _subscription(usage={"percent": 3, "isNegative": False}),
            _subscription(usage={"percent": 6, "isNegative": False}),
        ],
        battery_poll_interval_s=75.0,
    )

    client.generate(**_generate_kwargs(model="nai-diffusion-5-full"))

    # 75s 间隔按 30s 分片切分，等待中断最迟一个分片生效。
    assert clock.sleeps == [30.0, 30.0, 15.0]


def test_preflight_waits_for_battery_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock()
    client = _wait_client(
        monkeypatch,
        image_api=_FakeImageAPI(),
        clock=clock,
        responses=[
            _subscription(usage={"percent": 3, "isNegative": False}),
            _subscription(usage={"percent": 6, "isNegative": False}),
        ],
    )

    assert client.preflight(model="nai-diffusion-5-full") is None


def test_battery_wait_env_timeout_falls_back_to_hard_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOVELAI_BATTERY_WAIT_TIMEOUT_S", "0.01")
    image_api = _FakeImageAPI(images=[object()])
    clock = _FakeClock()
    low = _subscription(usage={"percent": 3, "isNegative": False})
    client = _wait_client(
        monkeypatch,
        image_api=image_api,
        clock=clock,
        responses=[low, low],
    )

    with pytest.raises(NovelAIAnlasGuardError):
        client.generate(**_generate_kwargs(model="nai-diffusion-5-full"))

    assert image_api.calls == []


def test_battery_wait_default_constants() -> None:
    assert novelai_client._DEFAULT_BATTERY_POLL_INTERVAL_S == 300.0
    assert novelai_client._DEFAULT_BATTERY_WAIT_TIMEOUT_S == 86400.0


def test_battery_poll_interval_must_be_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="NOVELAI_BATTERY_POLL_INTERVAL_S"):
        _make_client(
            monkeypatch,
            image_api=_FakeImageAPI(),
            user_api=_FakeUserAPI([]),
            battery_poll_interval_s=0.0,
        )


def test_v5_battery_above_threshold_allows_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(images=["img"])
    # percent=6 高于默认阈值 5：放行；仅生成前一次电量检查。
    user_api = _FakeUserAPI(
        [_subscription(usage={"percent": 6, "isNegative": False})]
    )
    client = _make_client(
        monkeypatch,
        image_api=image_api,
        user_api=user_api,
    )

    images = client.generate(**_generate_kwargs(model="nai-diffusion-5-full"))

    assert images == ["img"]
    assert len(image_api.calls) == 1
    assert user_api.calls == 1


def test_v5_logs_remaining_battery_before_generation(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    image_api = _FakeImageAPI(images=["img"])
    user_api = _FakeUserAPI(
        [_subscription(usage={"percent": 60, "isNegative": False})]
    )
    client = _make_client(
        monkeypatch,
        image_api=image_api,
        user_api=user_api,
    )
    caplog.set_level("INFO", logger=novelai_client.__name__)

    client.generate(**_generate_kwargs(model="nai-diffusion-5-full"))

    # 电量日志由生成前检查打印（复用同一次订阅响应，不额外查询）。
    assert "NovelAI V5 电池剩余：60.0%" in caplog.messages


def test_v45_generation_does_not_log_battery(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    image_api = _FakeImageAPI(images=["img"])
    user_api = _FakeUserAPI([_subscription(usage={"percent": 60})])
    client = _make_client(monkeypatch, image_api=image_api, user_api=user_api)
    caplog.set_level("INFO", logger=novelai_client.__name__)
    client.preflight()

    client.generate(**_generate_kwargs())

    assert not any("电池剩余" in msg for msg in caplog.messages)


# --- 启动预检 ---


def test_preflight_aborts_non_opus_key(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(
        monkeypatch,
        image_api=_FakeImageAPI(),
        user_api=_FakeUserAPI([_subscription(tier=2)]),
    )

    with pytest.raises(RuntimeError, match="非 Opus"):
        client.preflight()


def test_preflight_passes_for_opus_and_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client(
        monkeypatch,
        image_api=_FakeImageAPI(),
        user_api=_FakeUserAPI([_subscription()]),
    )

    assert client.preflight() is None


def test_preflight_hard_stop_mode_checks_battery_for_v5_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client(
        monkeypatch,
        image_api=_FakeImageAPI(),
        user_api=_FakeUserAPI([_subscription(usage={"percent": 0, "isNegative": False})]),
        battery_hard_stop=True,
    )

    with pytest.raises(NovelAIAnlasGuardError) as exc_info:
        client.preflight(model="nai-diffusion-5-full")

    assert exc_info.value.code == _GUARD_CODE_BATTERY_LOW


def test_preflight_skips_battery_check_for_v45_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # V4.5 不在电池政策内：usage 不可读也照常通过预检。
    client = _make_client(
        monkeypatch,
        image_api=_FakeImageAPI(),
        user_api=_FakeUserAPI([_subscription(usage="not-a-mapping")]),
    )

    assert client.preflight(model="nai-diffusion-4-5-full") is None


# --- 402 认证错误不再重试 ---


def test_authentication_error_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(
        errors=[
            AuthenticationError("Insufficient credits or subscription required"),
            AuthenticationError("Insufficient credits or subscription required"),
            AuthenticationError("Insufficient credits or subscription required"),
            AuthenticationError("Insufficient credits or subscription required"),
        ]
    )
    user_api = _FakeUserAPI([_subscription()])
    client = _make_client(monkeypatch, image_api=image_api, user_api=user_api)
    client.preflight()

    with pytest.raises(AuthenticationError):
        client.generate(**_generate_kwargs())

    # 默认 max_retries=3，认证类错误必须首试即败、不空转重试。
    assert len(image_api.calls) == 1


def test_rate_limit_error_still_retries_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_api = _FakeImageAPI(
        errors=[RateLimitError("Rate limit exceeded"), RateLimitError("Rate limit exceeded")]
    )
    user_api = _FakeUserAPI([_subscription()])
    client = _make_client(monkeypatch, image_api=image_api, user_api=user_api)
    # 429 走既有重试路径：冷却置零避免测试真实睡眠。
    client._rate_limit_cooldown = 0.0
    client.preflight()

    images = client.generate(**_generate_kwargs())

    assert images == []
    assert len(image_api.calls) == 3


# --- 守卫异常与错误序列化契约 ---


def _make_worker_plan(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "positive_prompt": "masterpiece,",
        "negative_prompt": None,
        "x_index": 0,
        "y_index": 1,
        "x_row": {},
        "y_value": "artist",
        "prompt_hash": "abc",
        "seed": 42,
        "generation_params": {},
        "workflow_hash": "wf",
        "save_image_prefix": "test",
        "x_description": {"zh": "", "en": ""},
        "attempt": 1,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _run_worker_once(worker: Any, tmp_path: Path, plan: argparse.Namespace) -> Any:
    args = argparse.Namespace(
        width=832,
        height=1216,
        steps=28,
        cfg=5.0,
        sampler_name="k_euler_ancestral",
        batch_size=1,
    )
    return worker(
        args,
        tmp_path,
        None,
        plan,
        None,
        None,
        lambda *a, **kw: "",
        None,
        None,
        lambda **kw: dict(kw),
        lambda: "2026-01-01T00:00:00",
    )


def test_guard_error_as_metadata_contract() -> None:
    exc = NovelAIAnlasGuardError(
        "V5 电量不足",
        code=_GUARD_CODE_BATTERY_LOW,
        context={"threshold_percent": 5.0},
    )

    metadata = exc.as_metadata()

    assert metadata == {
        "type": "anlas_guard",
        "code": _GUARD_CODE_BATTERY_LOW,
        "message": "V5 电量不足",
        "context": {"threshold_percent": 5.0},
    }


def test_worker_battery_low_records_failure_and_requests_abort(
    tmp_path: Path,
) -> None:
    class _GuardClient:
        def generate(self, **kwargs: Any) -> list[object]:
            _ = kwargs
            raise NovelAIAnlasGuardError(
                "V5 电量不足：usage.percent=3 低于阈值 5",
                code=_GUARD_CODE_BATTERY_LOW,
            )

    worker = novelai_client.novelai_worker(
        client=_GuardClient(), model="nai-diffusion-5-full"
    )
    outcome = _run_worker_once(worker, tmp_path, _make_worker_plan())

    record = outcome.record
    assert record is not None
    assert record["status"] == "failed"
    error = record["error"]
    assert isinstance(error, dict)
    # 错误码经 as_metadata() 进入 metadata.jsonl 的 error 字段，
    # 可被 --retry-error-code 精准捞回。
    assert error["type"] == "anlas_guard"
    assert error["code"] == _GUARD_CODE_BATTERY_LOW
    assert isinstance(error["message"], str)
    # 电量耗尽是运行级硬停信号：除记录失败外，还要求协调器停止提交后续单元格。
    assert outcome.abort is True


def test_worker_param_violation_does_not_request_abort(tmp_path: Path) -> None:
    class _ParamGuardClient:
        def generate(self, **kwargs: Any) -> list[object]:
            _ = kwargs
            raise NovelAIAnlasGuardError(
                "免费资格参数不合规：steps=30",
                code=_GUARD_CODE_PARAM_VIOLATION,
            )

    worker = novelai_client.novelai_worker(
        client=_ParamGuardClient(), model="nai-diffusion-4-5-full"
    )
    outcome = _run_worker_once(worker, tmp_path, _make_worker_plan())

    # 参数不合规是逐格失败，不是运行级硬停。
    assert outcome.abort is False
    assert outcome.record is not None
    assert outcome.record["status"] == "failed"


def test_worker_keeps_sdk_error_payload_shape_for_non_guard_errors(
    tmp_path: Path,
) -> None:
    from novelai.exceptions import ServerError

    class _FailingClient:
        def generate(self, **kwargs: Any) -> list[object]:
            _ = kwargs
            raise ServerError("Server error: 500")

    worker = novelai_client.novelai_worker(
        client=_FailingClient(), model="nai-diffusion-4-5-curated"
    )
    outcome = _run_worker_once(
        worker,
        tmp_path,
        _make_worker_plan(y_index=0, y_value="y", prompt_hash="h"),
    )
    outcome = _run_worker_once(
        worker,
        tmp_path,
        _make_worker_plan(y_index=0, y_value="y", prompt_hash="h"),
    )

    record = outcome.record
    assert record is not None
    error = record["error"]
    assert isinstance(error, dict)
    assert error["type"] == "api_error"
    assert outcome.abort is False


# --- 真实 SDK 模型的 usage 提取（pydantic extra 字段路径）---


def test_usage_extraction_supports_real_sdk_subscription_model() -> None:
    subscription = Subscription.model_validate(
        {
            "tier": 3,
            "active": True,
            "expiresAt": 9999999999,
            "perks": {},
            "trainingStepsLeft": {
                "fixedTrainingStepsLeft": 20,
                "purchasedTrainingSteps": 6,
            },
            "usage": {
                "percent": 42,
                "isNegative": False,
                "timeUntilNextPercent": 60000,
            },
        }
    )

    assert novelai_client._extract_usage_percent(subscription) == 42.0
    assert novelai_client._extract_usage_is_negative(subscription) is False
