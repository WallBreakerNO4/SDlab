# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportUnusedCallResult=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import importlib
import sys
import types
from pathlib import Path
from typing import Protocol, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_runner_config_stub() -> None:
    module = types.ModuleType("scripts.generation.runner_config")

    def load_runner_config(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        raise AssertionError("测试需显式 monkeypatch load_runner_config")

    setattr(module, "load_runner_config", load_runner_config)
    sys.modules["scripts.generation.runner_config"] = module


class _MainModule(Protocol):
    def main(self, argv: list[str] | None = None) -> int: ...


def _import_main_module() -> _MainModule:
    _install_runner_config_stub()
    _ = sys.modules.pop("main", None)
    _ = sys.modules.pop("scripts.generation.comfyui_part1_generate", None)
    return cast(_MainModule, cast(object, importlib.import_module("main")))


def test_main_requires_config_for_fresh_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main_module = _import_main_module()

    exit_code = main_module.main(["--dry-run", "--run-dir", str(tmp_path / "run")])

    assert exit_code == 2
    assert "fresh-run 模式必须提供 --config" in capsys.readouterr().err


def test_main_propagates_help_to_script_runner() -> None:
    main_module = _import_main_module()

    with pytest.raises(SystemExit) as exc_info:
        _ = main_module.main(["--help"])

    assert exc_info.value.code == 0


def test_main_propagates_invalid_args_exit_code() -> None:
    main_module = _import_main_module()

    with pytest.raises(SystemExit) as exc_info:
        _ = main_module.main(["--invalid-arg"])

    assert exc_info.value.code == 2
