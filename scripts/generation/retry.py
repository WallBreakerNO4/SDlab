import random
import time
from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")


def _compute_wait_with_full_jitter(
    *,
    retry_index: int,
    base_delay_s: float,
    max_delay_per_sleep_s: float,
    random_fn: Callable[[], float],
) -> float:
    exponential_multiplier = 1.0
    for _ in range(retry_index - 1):
        exponential_multiplier *= 2.0
    exponential_cap = base_delay_s * exponential_multiplier
    cap = exponential_cap
    if cap > max_delay_per_sleep_s:
        cap = max_delay_per_sleep_s
    ratio = float(random_fn())
    if ratio < 0.0:
        ratio = 0.0
    if ratio > 1.0:
        ratio = 1.0
    return float(cap * ratio)


def retry_call(
    operation: Callable[[], T],
    *,
    retry_exceptions: tuple[type[Exception], ...] = (Exception,),
    max_attempts: int | None = 5,
    stop_after_delay_s: float | None = 30.0,
    base_delay_s: float = 0.25,
    max_delay_per_sleep_s: float = 5.0,
    sleep: Callable[[float], None] | None = None,
    monotonic: Callable[[], float] | None = None,
    random_fn: Callable[[], float] | None = None,
) -> T:
    if max_attempts is not None and max_attempts <= 0:
        raise ValueError("max_attempts must be greater than 0")
    if stop_after_delay_s is not None and stop_after_delay_s < 0:
        raise ValueError("stop_after_delay_s must be >= 0")
    if base_delay_s <= 0:
        raise ValueError("base_delay_s must be greater than 0")
    if max_delay_per_sleep_s <= 0:
        raise ValueError("max_delay_per_sleep_s must be greater than 0")
    if not retry_exceptions:
        raise ValueError("retry_exceptions must not be empty")

    sleep_fn = time.sleep if sleep is None else sleep
    monotonic_fn = time.monotonic if monotonic is None else monotonic
    random_value_fn = random.random if random_fn is None else random_fn

    deadline_s: float | None = None
    if stop_after_delay_s is not None:
        deadline_s = monotonic_fn() + stop_after_delay_s

    attempts = 0
    while True:
        attempts += 1
        try:
            return operation()
        except retry_exceptions:
            if max_attempts is not None and attempts >= max_attempts:
                raise

            remaining_budget_s: float | None = None
            if deadline_s is not None:
                remaining_budget_s = deadline_s - monotonic_fn()
                if remaining_budget_s <= 0:
                    raise

            planned_wait_s = _compute_wait_with_full_jitter(
                retry_index=attempts,
                base_delay_s=base_delay_s,
                max_delay_per_sleep_s=max_delay_per_sleep_s,
                random_fn=random_value_fn,
            )

            if remaining_budget_s is not None:
                planned_wait_s = min(planned_wait_s, remaining_budget_s)

            if planned_wait_s > 0:
                sleep_fn(planned_wait_s)
