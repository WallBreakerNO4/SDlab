from __future__ import annotations

from dataclasses import dataclass
import importlib
import sys
from pathlib import Path

import main as main_module
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _TTYStream:
    def __init__(self, is_tty: bool) -> None:
        self._is_tty = is_tty
        self._chunks: list[str] = []

    def isatty(self) -> bool:
        return self._is_tty

    def write(self, text: str) -> int:
        self._chunks.append(text)
        return len(text)

    def flush(self) -> None:
        return None

    def getvalue(self) -> str:
        return "".join(self._chunks)


class _FakePrompt:
    def __init__(self, value: object) -> None:
        self._value = value

    def ask(self) -> object:
        return self._value


@dataclass
class _FakeChoice:
    title: str
    value: str


class _FakeQuestionary:
    Choice = _FakeChoice

    def __init__(
        self, *, selects: list[object], texts: list[object], confirms: list[object]
    ) -> None:
        self._selects = iter(selects)
        self._texts = iter(texts)
        self._confirms = iter(confirms)

    def select(self, _message: str, *, choices: list[_FakeChoice]) -> _FakePrompt:
        _ = choices
        return _FakePrompt(next(self._selects))

    def text(self, _message: str, *, default: str = "") -> _FakePrompt:
        _ = default
        return _FakePrompt(next(self._texts))

    def confirm(self, _message: str, *, default: bool) -> _FakePrompt:
        _ = default
        return _FakePrompt(next(self._confirms))


def _patch_stdio_tty(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stdin_tty: bool,
    stdout_tty: bool,
) -> _TTYStream:
    stdin_stream = _TTYStream(stdin_tty)
    stdout_stream = _TTYStream(stdout_tty)
    monkeypatch.setattr(sys, "stdin", stdin_stream)
    monkeypatch.setattr(sys, "stdout", stdout_stream)
    return stdout_stream


def test_main_no_args_and_tty_enters_menu_and_can_quit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _patch_stdio_tty(monkeypatch, stdin_tty=True, stdout_tty=True)
    fake_questionary = _FakeQuestionary(selects=["__exit__"], texts=[], confirms=[])
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    called = {"generate": False}

    def _fake_generate(_argv: list[str] | None) -> int:
        called["generate"] = True
        return 99

    monkeypatch.setattr(main_module, "generate_main", _fake_generate)
    exit_code = main_module.main([])

    assert exit_code == 0
    assert called["generate"] is False


def test_main_menu_convert_uses_dotenv_default_csv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    stdout_stream = _patch_stdio_tty(monkeypatch, stdin_tty=True, stdout_tty=True)
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".env").write_text(
        "CONVERT_Y_DEFAULT_CSV=from-dotenv.csv\n",
        encoding="utf-8",
    )
    fake_questionary = _FakeQuestionary(
        selects=["other", "csv_to_yaml", "convert_y_csv", "__exit__"],
        texts=["from-dotenv.csv"],
        confirms=[True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    captured: dict[str, list[str] | None] = {"argv": None}

    def _fake_convert_y_main(argv: list[str] | None) -> int:
        captured["argv"] = argv
        return 0

    convert_y_module = importlib.import_module("scripts.other.convert_y_csv_to_json")
    monkeypatch.setattr(convert_y_module, "main", _fake_convert_y_main)

    exit_code = main_module.main([])

    assert exit_code == 0
    assert captured["argv"] == ["from-dotenv.csv"]
    assert (
        "预览命令: uv run python scripts/other/convert_y_csv_to_json.py from-dotenv.csv"
        in stdout_stream.getvalue()
    )


def test_main_menu_flag_non_tty_prints_reason_and_returns_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout_stream = _patch_stdio_tty(monkeypatch, stdin_tty=False, stdout_tty=False)
    exit_code = main_module.main(["--menu"])

    assert exit_code == 2
    assert "--menu requires an interactive TTY" in stdout_stream.getvalue()


def test_main_passthrough_when_non_menu_args_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _patch_stdio_tty(monkeypatch, stdin_tty=True, stdout_tty=True)
    captured: dict[str, list[str] | None] = {"argv": None}

    def _fake_generate(argv: list[str] | None) -> int:
        captured["argv"] = argv
        return 7

    monkeypatch.setattr(main_module, "generate_main", _fake_generate)
    exit_code = main_module.main(["--dry-run", "--x-limit", "1"])

    assert exit_code == 7
    assert captured["argv"] == ["--dry-run", "--x-limit", "1"]
