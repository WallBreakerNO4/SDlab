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
from scripts.cli.registry import iter_entries


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


def test_r2_upload_menu_entry_exists() -> None:
    entries = list(iter_entries(include_disabled=True))
    entry = next((item for item in entries if item.key == "upload_r2"), None)

    assert entry is not None
    assert entry.label == "上传到 R2"
    assert entry.entrypoint == "scripts.r2_upload.upload_images_to_r2:main"


def test_upload_basic_flow_uses_selected_run_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "comfyui_api_outputs" / "run-a").mkdir(parents=True)
    calls: list[list[str] | None] = []

    def _fake_upload_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr("scripts.r2_upload.upload_images_to_r2.main", _fake_upload_main)
    fake_questionary = _FakeQuestionary(
        selects=["upload", "run-a", "__exit__"],
        texts=[],
        confirms=[False, True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(MenuIO(print_func=outputs.append))

    assert exit_code == 0
    assert calls == [["--run-dir", "run-a"]]
    assert any(
        "预览命令: uv run python scripts/r2_upload/upload_images_to_r2.py --run-dir run-a"
        in output
        for output in outputs
    )


def test_upload_advanced_flow_collects_optional_args(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "comfyui_api_outputs" / "run-b").mkdir(parents=True)
    calls: list[list[str] | None] = []

    def _fake_upload_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 5

    monkeypatch.setattr("scripts.r2_upload.upload_images_to_r2.main", _fake_upload_main)
    fake_questionary = _FakeQuestionary(
        selects=["upload", "run-b", "advance", "__exit__"],
        texts=["custom-root", "4", "12"],
        confirms=[True, True, True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(MenuIO(print_func=outputs.append))

    assert exit_code == 0
    assert calls == [
        [
            "--run-dir",
            "run-b",
            "--run-root",
            "custom-root",
            "--dry-run",
            "--category",
            "advance",
            "--concurrency",
            "4",
            "--limit",
            "12",
        ]
    ]
    assert "上传完成，退出码: 5" in outputs


def test_upload_menu_uses_comfyui_out_dir_for_run_discovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    custom_root = tmp_path / "custom-outputs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COMFYUI_OUT_DIR", str(custom_root))
    (custom_root / "run-env").mkdir(parents=True)
    calls: list[list[str] | None] = []

    def _fake_upload_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr("scripts.r2_upload.upload_images_to_r2.main", _fake_upload_main)
    fake_questionary = _FakeQuestionary(
        selects=["upload", "run-env", "__exit__"],
        texts=[],
        confirms=[False, True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(MenuIO(print_func=outputs.append))

    assert exit_code == 0
    assert calls == [["--run-dir", "run-env"]]


def test_upload_without_run_dirs_prints_hint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    fake_questionary = _FakeQuestionary(
        selects=["upload", "__exit__"], texts=[], confirms=[]
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(MenuIO(print_func=outputs.append))

    assert exit_code == 0
    assert "未找到可上传的生成结果目录（comfyui_api_outputs/）。" in outputs


def test_upload_without_run_dirs_prints_env_specific_hint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    custom_root = tmp_path / "custom-outputs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COMFYUI_OUT_DIR", str(custom_root))
    fake_questionary = _FakeQuestionary(
        selects=["upload", "__exit__"], texts=[], confirms=[]
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(MenuIO(print_func=outputs.append))

    assert exit_code == 0
    assert f"未找到可上传的生成结果目录（{custom_root.as_posix()}/）。" in outputs
