from __future__ import annotations

from dataclasses import dataclass, field
import sys
from typing import Callable

InputFunc = Callable[[str], str]
PrintFunc = Callable[[str], None]
IsATTYFunc = Callable[[], bool]


def _stdin_isatty() -> bool:
    stream = getattr(sys, "stdin", None)
    checker = getattr(stream, "isatty", None)
    if not callable(checker):
        return False
    return bool(checker())


def _stdout_isatty() -> bool:
    stream = getattr(sys, "stdout", None)
    checker = getattr(stream, "isatty", None)
    if not callable(checker):
        return False
    return bool(checker())


@dataclass(slots=True)
class MenuIO:
    input_func: InputFunc = field(default_factory=lambda: input)
    print_func: PrintFunc = field(default_factory=lambda: print)
    stdin_isatty: IsATTYFunc = _stdin_isatty
    stdout_isatty: IsATTYFunc = _stdout_isatty

    def read(self, prompt: str = "") -> str:
        return self.input_func(prompt)

    def write(self, message: str) -> None:
        self.print_func(message)

    def is_interactive(self) -> bool:
        return self.stdin_isatty() and self.stdout_isatty()
