# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.generation.retry as retry


class MutableClock:
    now: float

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_retry_call_uses_exponential_backoff_with_full_jitter() -> None:
    attempts = 0
    waits: list[float] = []
    random_values = iter([1.0, 0.5, 0.25])

    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise TimeoutError("transient")
        return "ok"

    result = retry.retry_call(
        flaky,
        max_attempts=4,
        base_delay_s=1.0,
        max_delay_per_sleep_s=4.0,
        sleep=waits.append,
        random_fn=lambda: next(random_values),
    )

    assert result == "ok"
    assert attempts == 4
    assert waits == [1.0, 1.0, 1.0]


def test_retry_call_stops_after_max_attempts_including_first() -> None:
    attempts = 0
    waits: list[float] = []

    def always_fail() -> None:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("boom")

    with pytest.raises(TimeoutError, match="boom"):
        _ = retry.retry_call(
            always_fail,
            max_attempts=3,
            base_delay_s=0.2,
            max_delay_per_sleep_s=2.0,
            sleep=waits.append,
            random_fn=lambda: 1.0,
        )

    assert attempts == 3
    assert waits == [0.2, 0.4]


def test_retry_call_stops_after_total_budget_and_raises_last_error() -> None:
    attempts = 0
    waits: list[float] = []
    clock = MutableClock(now=0.0)

    def fail_with_attempt_number() -> None:
        nonlocal attempts
        attempts += 1
        raise TimeoutError(f"attempt-{attempts}")

    def fake_sleep(seconds: float) -> None:
        waits.append(seconds)
        clock.sleep(seconds)

    with pytest.raises(TimeoutError, match="attempt-3"):
        _ = retry.retry_call(
            fail_with_attempt_number,
            stop_after_delay_s=0.25,
            max_attempts=10,
            base_delay_s=0.2,
            max_delay_per_sleep_s=2.0,
            monotonic=clock.monotonic,
            sleep=fake_sleep,
            random_fn=lambda: 1.0,
        )

    assert attempts == 3
    assert waits == pytest.approx([0.2, 0.05])
    assert clock.now == pytest.approx(0.25)


def test_retry_call_uses_monkeypatched_time_without_real_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []
    clock = MutableClock(now=10.0)
    attempts = 0

    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("once")
        return "ok"

    def fake_sleep(seconds: float) -> None:
        waits.append(seconds)
        clock.sleep(seconds)

    monkeypatch.setattr("scripts.generation.retry.time.sleep", fake_sleep)
    monkeypatch.setattr("scripts.generation.retry.time.monotonic", clock.monotonic)
    monkeypatch.setattr("scripts.generation.retry.random.random", lambda: 0.5)

    result = retry.retry_call(
        flaky,
        max_attempts=2,
        base_delay_s=0.4,
        max_delay_per_sleep_s=1.0,
    )

    assert result == "ok"
    assert waits == [0.2]


def test_retry_call_does_not_retry_unlisted_exception_type() -> None:
    attempts = 0
    waits: list[float] = []

    def fail_with_value_error() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("fatal")

    with pytest.raises(ValueError, match="fatal"):
        _ = retry.retry_call(
            fail_with_value_error,
            retry_exceptions=(TimeoutError,),
            max_attempts=5,
            sleep=waits.append,
        )

    assert attempts == 1
    assert waits == []
