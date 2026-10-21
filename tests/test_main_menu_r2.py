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
    (tmp_path / "outputs" / "run-a").mkdir(parents=True)
    calls: list[list[str] | None] = []

    def _fake_upload_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr("scripts.r2_upload.upload_images_to_r2.main", _fake_upload_main)
    fake_questionary = _FakeQuestionary(
        selects=["upload", "run-a", "normal", "remote", "__exit__"],
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


def test_upload_force_publish_mode_adds_short_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs" / "run-force").mkdir(parents=True)
    calls: list[list[str] | None] = []

    def _fake_upload_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr("scripts.r2_upload.upload_images_to_r2.main", _fake_upload_main)
    fake_questionary = _FakeQuestionary(
        selects=["upload", "run-force", "force", "remote", "__exit__"],
        texts=[],
        confirms=[False, True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    exit_code = run_menu(MenuIO(print_func=lambda value: None))

    assert exit_code == 0
    assert calls == [["--run-dir", "run-force", "-F"]]


def test_upload_advanced_flow_collects_optional_args(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs" / "run-b").mkdir(parents=True)
    calls: list[list[str] | None] = []

    def _fake_upload_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 5

    monkeypatch.setattr("scripts.r2_upload.upload_images_to_r2.main", _fake_upload_main)
    fake_questionary = _FakeQuestionary(
        selects=["upload", "run-b", "normal", "remote", "advance", "__exit__"],
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
        selects=["upload", "run-env", "normal", "remote", "__exit__"],
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
    assert "未找到可上传的生成结果目录（outputs/）。" in outputs


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


def test_upload_local_mode_passes_local_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs" / "run-local").mkdir(parents=True)
    calls: list[list[str] | None] = []

    def _fake_upload_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr("scripts.r2_upload.upload_images_to_r2.main", _fake_upload_main)
    fake_questionary = _FakeQuestionary(
        selects=["upload", "run-local", "normal", "local", "__exit__"],
        texts=[],
        confirms=[False, True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(MenuIO(print_func=outputs.append))

    assert exit_code == 0
    assert calls == [["--run-dir", "run-local", "--local"]]
    assert any("--local" in output for output in outputs)


def test_delete_menu_remote_mode_does_not_pass_local_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str] | None] = []
    list_calls: list[bool] = []

    def _fake_list_db_runs(*, local: bool = False) -> list[str]:
        list_calls.append(local)
        return ["run-a"]

    def _fake_delete_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(
        "scripts.r2_upload.delete_run.list_db_runs", _fake_list_db_runs
    )
    monkeypatch.setattr("scripts.r2_upload.delete_run.main", _fake_delete_main)
    fake_questionary = _FakeQuestionary(
        selects=["other", "delete_run", "remote", "run-a", "__exit__"],
        texts=[],
        confirms=[True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(MenuIO(print_func=outputs.append))

    assert exit_code == 0
    assert list_calls == [False]
    assert calls == [["--run-dir", "run-a"]]
    assert any("R2: runs/run-a/" in output for output in outputs)


def test_delete_menu_local_mode_passes_local_flag_and_skips_r2_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str] | None] = []
    list_calls: list[bool] = []

    def _fake_list_db_runs(*, local: bool = False) -> list[str]:
        list_calls.append(local)
        return ["run-local"]

    def _fake_delete_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(
        "scripts.r2_upload.delete_run.list_db_runs", _fake_list_db_runs
    )
    monkeypatch.setattr("scripts.r2_upload.delete_run.main", _fake_delete_main)
    fake_questionary = _FakeQuestionary(
        selects=["other", "delete_run", "local", "run-local", "__exit__"],
        texts=[],
        confirms=[True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    outputs: list[str] = []
    exit_code = run_menu(MenuIO(print_func=outputs.append))

    assert exit_code == 0
    assert list_calls == [True]
    assert calls == [["--run-dir", "run-local", "--local"]]
    assert any("已跳过 R2 对象删除" in output for output in outputs)


def test_backfill_menu_entry_exists() -> None:
    entries = list(iter_entries(include_disabled=True))
    entry = next((item for item in entries if item.key == "backfill_style_items"), None)

    assert entry is not None
    assert entry.entrypoint == "scripts.other.backfill_run_style_items:main"


def test_backfill_menu_local_mode_passes_local_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str] | None] = []

    def _fake_backfill_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(
        "scripts.other.backfill_run_style_items.main", _fake_backfill_main
    )
    fake_questionary = _FakeQuestionary(
        selects=["other", "backfill_style_items", "local", "__exit__"],
        texts=[],
        confirms=[True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    exit_code = run_menu(MenuIO(print_func=lambda value: None))

    assert exit_code == 0
    assert calls == [["--local"]]


def test_backfill_menu_remote_mode_omits_local_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str] | None] = []

    def _fake_backfill_main(argv: list[str] | None = None) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(
        "scripts.other.backfill_run_style_items.main", _fake_backfill_main
    )
    fake_questionary = _FakeQuestionary(
        selects=["other", "backfill_style_items", "remote", "__exit__"],
        texts=[],
        confirms=[True],
    )
    monkeypatch.setattr("scripts.cli.menu._load_questionary", lambda: fake_questionary)

    exit_code = run_menu(MenuIO(print_func=lambda value: None))

    assert exit_code == 0
    assert calls == [[]]
