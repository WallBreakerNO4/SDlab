from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cli.io import MenuIO
from scripts.cli.menu import run_menu


class _FakePrompt:
    def __init__(self, value: object) -> None:
        self._value = value

    def ask(self) -> object:
        if isinstance(self._value, BaseException):
            raise self._value
        return self._value


@dataclass
class _FakeChoice:
    title: str
    value: str


class _FakeQuestionary:
    Choice = _FakeChoice

    def __init__(
        self,
        *,
        selects: list[object] | None = None,
        texts: list[object] | None = None,
        confirms: list[object] | None = None,
    ) -> None:
        self._selects = iter(selects or [])
        self._texts = iter(texts or [])
        self._confirms = iter(confirms or [])

    def select(self, _message: str, *, choices: list[_FakeChoice]) -> _FakePrompt:
        _ = choices
        return _FakePrompt(next(self._selects))

    def text(self, _message: str, *, default: str = "") -> _FakePrompt:
        _ = default
        return _FakePrompt(next(self._texts))

    def confirm(self, _message: str, *, default: bool) -> _FakePrompt:
        _ = default
        return _FakePrompt(next(self._confirms))


def _build_menu_io(outputs: list[str]) -> MenuIO:
    return MenuIO(print_func=outputs.append)


def test_generate_basic_flow_uses_selected_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str] | None] = []

    def _fake_generate_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(
        "scripts.generation.comfyui_part1_generate.main",
        _fake_generate_main,
    )
    fake_questionary = _FakeQuestionary(
        selects=["generate", "data/models/example/config.yaml", "__exit__"],
        confirms=[False, True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(_build_menu_io(outputs))

    assert exit_code == 0
    assert calls == [["--config", "data/models/example/config.yaml"]]
    assert any(
        "预览命令: uv run python scripts/generation/comfyui_part1_generate.py --config data/models/example/config.yaml"
        in output
        for output in outputs
    )
    assert "生图完成，退出码: 0" in outputs


def test_generate_advanced_flow_maps_original_cli_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str] | None] = []

    def _fake_generate_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 7

    monkeypatch.setattr(
        "scripts.generation.comfyui_part1_generate.main",
        _fake_generate_main,
    )
    fake_questionary = _FakeQuestionary(
        selects=["generate", "data/models/test/config.yaml", "__exit__"],
        texts=[
            "custom-run",
            "TEMP,AUTH",
            "http://127.0.0.1:8188",
            "12",
            "45",
            "180",
            "3",
            "2",
            "client-123",
        ],
        confirms=[True, True, True, False, True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(_build_menu_io(outputs))

    assert exit_code == 0
    assert calls == [
        [
            "--config",
            "data/models/test/config.yaml",
            "--dry-run",
            "--run-dir",
            "custom-run",
            "--retry-failed",
            "--retry-error-code",
            "TEMP,AUTH",
            "--base-url",
            "http://127.0.0.1:8188",
            "--request-timeout-s",
            "12",
            "--download-read-timeout-s",
            "45",
            "--job-timeout-s",
            "180",
            "--concurrency",
            "3",
            "--download-concurrency",
            "2",
            "--client-id",
            "client-123",
        ]
    ]
    assert "生图完成，退出码: 7" in outputs


def test_generate_novelai_advanced_flow_maps_retry_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str] | None] = []

    def _fake_novelai_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(
        "scripts.generation.novelai_generate.main",
        _fake_novelai_main,
    )
    fake_questionary = _FakeQuestionary(
        selects=[
            "generate_novelai",
            "data/models/nai-diffusion-5-full/config.yaml",
            "__exit__",
        ],
        texts=[
            "outputs/hard-stopped-run",
            "",
            "",
            "",
        ],
        confirms=[
            True,  # 开启高级参数
            False,  # dry-run
            True,  # --retry-failed
            False,  # --retry-incomplete
            True,  # 确认执行
        ],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(_build_menu_io(outputs))

    assert exit_code == 0
    assert calls == [
        [
            "--config",
            "data/models/nai-diffusion-5-full/config.yaml",
            "--run-dir",
            "outputs/hard-stopped-run",
            "--retry-failed",
        ]
    ]
    assert "NovelAI 生图完成，退出码: 0" in outputs


def test_generate_novelai_advanced_flow_maps_retry_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str] | None] = []

    def _fake_novelai_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(
        "scripts.generation.novelai_generate.main",
        _fake_novelai_main,
    )
    fake_questionary = _FakeQuestionary(
        selects=[
            "generate_novelai",
            "data/models/nai-diffusion-5-curated/config.yaml",
            "__exit__",
        ],
        texts=[
            "my-run",
            "anlas_battery_low,anlas_billing_detected",
            "",
            "",
        ],
        confirms=[
            True,  # 开启高级参数
            True,  # dry-run
            True,  # --retry-failed
            True,  # --retry-incomplete
            True,  # 确认执行
        ],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(_build_menu_io(outputs))

    assert exit_code == 0
    assert calls == [
        [
            "--config",
            "data/models/nai-diffusion-5-curated/config.yaml",
            "--dry-run",
            "--run-dir",
            "my-run",
            "--retry-failed",
            "--retry-incomplete",
            "--retry-error-code",
            "anlas_battery_low,anlas_billing_detected",
        ]
    ]
