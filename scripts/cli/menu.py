from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import shlex
from typing import Any, cast

from scripts.generation.comfyui_part1_generate import (
    build_parser as build_generate_parser,
)
from scripts.r2_upload.upload_images_to_r2 import build_parser as build_upload_parser
from scripts.r2_upload.upload_runtime import _resolve_default_run_root
from scripts.run_config_path import DATA_MODELS_DIR, iter_run_config_files

from .io import MenuIO
from .registry import ScriptMain, get_entry, load_entrypoint

DEFAULT_CONVERT_X_CSV = "data/prompts/X/common_prompts.csv"
DEFAULT_CONVERT_Y_CSV = "data/prompts/Y/300_NAI_Styles_Table-test.csv"
DEFAULT_ANNOTATE_Y_YAML = "data/prompts/Y/300_NAI_Styles_Table.yaml"
CONVERT_X_DEFAULT_ENV = "CONVERT_X_DEFAULT_CSV"
CONVERT_Y_DEFAULT_ENV = "CONVERT_Y_DEFAULT_CSV"
ANNOTATE_Y_DEFAULT_ENV = "ANNOTATE_Y_DEFAULT_YAML"

GENERATE_BASE_COMMAND = "uv run python scripts/generation/comfyui_part1_generate.py"
GENERATE_NOVELAI_BASE_COMMAND = "uv run python scripts/generation/novelai_generate.py"
UPLOAD_BASE_COMMAND = "uv run python scripts/r2_upload/upload_images_to_r2.py"
CONVERT_X_BASE_COMMAND = "uv run python scripts/other/convert_x_csv_to_json.py"
CONVERT_Y_BASE_COMMAND = "uv run python scripts/other/convert_y_csv_to_json.py"
ANNOTATE_Y_BASE_COMMAND = (
    "uv run python scripts/other/annotate_y_tag_types_from_danbooru.py"
)
CLEAR_R2_BASE_COMMAND = "uv run python scripts/r2_upload/clear_bucket.py"
DELETE_RUN_BASE_COMMAND = "uv run python -m scripts.r2_upload.delete_run --run-dir"


@dataclass(frozen=True, slots=True)
class MenuChoice:
    value: str
    title: str


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    entry_key: str
    argv: list[str]
    base_command: str
    success_prefix: str
    cancel_message: str

    @property
    def preview_command(self) -> str:
        if not self.argv:
            return self.base_command
        return f"{self.base_command} {shlex.join(self.argv)}"


class MenuAbort(Exception):
    def __init__(self, exit_code: int) -> None:
        super().__init__(exit_code)
        self.exit_code = exit_code


class QuestionaryMenuBackend:
    def __init__(self, io: MenuIO) -> None:
        self._io = io

    def select(
        self,
        message: str,
        choices: Sequence[MenuChoice],
        *,
        allow_back: bool = False,
        allow_exit: bool = False,
    ) -> str:
        questionary = _load_questionary()
        rendered = [
            questionary.Choice(title=choice.title, value=choice.value)
            for choice in choices
        ]
        if allow_back:
            rendered.append(questionary.Choice(title="返回上一级", value="__back__"))
        if allow_exit:
            rendered.append(questionary.Choice(title="退出", value="__exit__"))
        try:
            result = questionary.select(message, choices=rendered).ask()
        except KeyboardInterrupt as exc:
            raise MenuAbort(130) from exc
        if result is None:
            raise MenuAbort(0)
        return str(result)

    def text(self, message: str, *, default: str = "") -> str:
        questionary = _load_questionary()
        try:
            result = questionary.text(message, default=default).ask()
        except KeyboardInterrupt as exc:
            raise MenuAbort(130) from exc
        if result is None:
            raise MenuAbort(0)
        return str(result).strip()

    def confirm(self, message: str, *, default: bool) -> bool:
        questionary = _load_questionary()
        try:
            result = questionary.confirm(message, default=default).ask()
        except KeyboardInterrupt as exc:
            raise MenuAbort(130) from exc
        if result is None:
            raise MenuAbort(0)
        return bool(result)

    def write(self, message: str) -> None:
        self._io.write(message)


def run_menu(io: MenuIO) -> int:
    backend = QuestionaryMenuBackend(io)
    backend.write("")
    backend.write("脚本菜单：生图 / 上传 / 其他")
    backend.write("生图会先选择 data/models/ 下的配置；上传会先选择生成结果。")
    backend.write("")

    try:
        while True:
            selected = backend.select(
                "主菜单",
                [
                    MenuChoice("generate", "生图 (ComfyUI)"),
                    MenuChoice("generate_novelai", "生图 (NovelAI)"),
                    MenuChoice("upload", "上传"),
                    MenuChoice("other", "其他"),
                ],
                allow_exit=True,
            )
            if selected == "__exit__":
                return 0
            if selected == "generate":
                _handle_generate(backend)
                continue
            if selected == "generate_novelai":
                _handle_generate_novelai(backend)
                continue
            if selected == "upload":
                _handle_upload(backend)
                continue
            if selected == "other":
                _handle_other(backend)
                continue
        return 0
    except MenuAbort as exc:
        return exc.exit_code


def _load_questionary() -> Any:
    return cast(Any, importlib.import_module("questionary"))


def _handle_generate(backend: QuestionaryMenuBackend) -> None:
    config_files = _list_config_files()
    if not config_files:
        backend.write("未找到 data/models/ 下的运行配置。")
        return

    selected = backend.select(
        "选择运行配置",
        [
            MenuChoice(path.as_posix(), path.relative_to(DATA_MODELS_DIR).as_posix())
            for path in config_files
        ],
        allow_back=True,
    )
    if selected == "__back__":
        return

    argv = ["--config", selected]
    if backend.confirm("是否开启高级参数？", default=False):
        argv.extend(_prompt_generate_advanced_args(backend))

    _confirm_and_execute(
        backend,
        ExecutionPlan(
            entry_key="generate_grid",
            argv=argv,
            base_command=GENERATE_BASE_COMMAND,
            success_prefix="生图完成，退出码: ",
            cancel_message="已取消生图。",
        ),
    )


def _handle_generate_novelai(backend: QuestionaryMenuBackend) -> None:
    config_files = _list_config_files()
    if not config_files:
        backend.write("未找到 data/models/ 下的运行配置。")
        return

    novelai_configs = [
        path
        for path in config_files
        if _is_novelai_config(path)
    ]
    if not novelai_configs:
        backend.write(
            "未找到 NovelAI 运行配置。"
            " 请在 data/models/ 下创建 schema_version=image-run-config/v2 + backend=novelai 的配置。"
        )
        return

    selected = backend.select(
        "选择运行配置",
        [
            MenuChoice(path.as_posix(), path.relative_to(DATA_MODELS_DIR).as_posix())
            for path in novelai_configs
        ],
        allow_back=True,
    )
    if selected == "__back__":
        return

    argv = ["--config", selected]
    if backend.confirm("是否开启高级参数？", default=False):
        argv.extend(_prompt_generate_novelai_advanced_args(backend))

    _confirm_and_execute(
        backend,
        ExecutionPlan(
            entry_key="generate_novelai",
            argv=argv,
            base_command=GENERATE_NOVELAI_BASE_COMMAND,
            success_prefix="NovelAI 生图完成，退出码: ",
            cancel_message="已取消 NovelAI 生图。",
        ),
    )


def _handle_upload(backend: QuestionaryMenuBackend) -> None:
    upload_run_root = Path(_resolve_default_run_root())
    run_dirs = _list_run_dirs(upload_run_root)
    if not run_dirs:
        backend.write(f"未找到可上传的生成结果目录（{upload_run_root.as_posix()}/）。")
        return

    selected = backend.select(
        "选择要上传的生成结果",
        [MenuChoice(path.name, path.name) for path in run_dirs],
        allow_back=True,
    )
    if selected == "__back__":
        return

    argv = ["--run-dir", selected]
    if backend.confirm("是否开启高级参数？", default=False):
        argv.extend(_prompt_upload_advanced_args(backend))

    _confirm_and_execute(
        backend,
        ExecutionPlan(
            entry_key="upload_r2",
            argv=argv,
            base_command=UPLOAD_BASE_COMMAND,
            success_prefix="上传完成，退出码: ",
            cancel_message="已取消上传。",
        ),
    )


def _handle_other(backend: QuestionaryMenuBackend) -> None:
    selected = backend.select(
        "其他功能",
        [
            MenuChoice("csv_to_yaml", "CSV to YAML 脚本"),
            MenuChoice("annotate_y_tag_types", "标注 Y YAML tag 类型（Danbooru）"),
            MenuChoice("delete_run", "删除 Run（数据库 + R2）"),
            MenuChoice("clear_r2", "R2 清空脚本"),
        ],
        allow_back=True,
    )
    if selected == "__back__":
        return
    if selected == "csv_to_yaml":
        _handle_csv_to_yaml(backend)
        return
    if selected == "annotate_y_tag_types":
        _handle_annotate_y_tag_types(backend)
        return
    if selected == "delete_run":
        _handle_delete_run(backend)
        return
    if selected == "clear_r2":
        _handle_clear_r2(backend)


def _handle_csv_to_yaml(backend: QuestionaryMenuBackend) -> None:
    selected = backend.select(
        "选择 CSV 转 YAML 脚本",
        [
            MenuChoice("convert_x_csv", "X CSV 转 YAML"),
            MenuChoice("convert_y_csv", "Y CSV 转 YAML"),
        ],
        allow_back=True,
    )
    if selected == "__back__":
        return
    if selected == "convert_x_csv":
        csv_path = backend.text(
            "输入 X CSV 路径（留空使用默认值）",
            default=_default_convert_x_csv(),
        )
        _confirm_and_execute(
            backend,
            ExecutionPlan(
                entry_key="convert_x_csv",
                argv=[csv_path],
                base_command=CONVERT_X_BASE_COMMAND,
                success_prefix="转换完成，退出码: ",
                cancel_message="已取消转换。",
            ),
        )
        return

    csv_path = backend.text(
        "输入 Y CSV 路径（留空使用默认值）",
        default=_default_convert_y_csv(),
    )
    _confirm_and_execute(
        backend,
        ExecutionPlan(
            entry_key="convert_y_csv",
            argv=[csv_path],
            base_command=CONVERT_Y_BASE_COMMAND,
            success_prefix="转换完成，退出码: ",
            cancel_message="已取消转换。",
        ),
    )


def _handle_annotate_y_tag_types(backend: QuestionaryMenuBackend) -> None:
    yaml_path = backend.text(
        "输入 Y YAML 路径（留空使用默认值）",
        default=_default_annotate_y_yaml(),
    )
    mode = backend.select(
        "选择执行方式",
        [
            MenuChoice("in_place", "覆盖原 YAML"),
            MenuChoice("dry_run", "只预览"),
        ],
        allow_back=True,
    )
    if mode == "__back__":
        return

    argv = [yaml_path]
    if mode == "in_place":
        argv.append("--in-place")
    else:
        argv.append("--dry-run")

    _confirm_and_execute(
        backend,
        ExecutionPlan(
            entry_key="annotate_y_tag_types",
            argv=argv,
            base_command=ANNOTATE_Y_BASE_COMMAND,
            success_prefix="标注完成，退出码: ",
            cancel_message="已取消标注。",
        ),
    )


def _handle_clear_r2(backend: QuestionaryMenuBackend) -> None:
    selected = backend.select(
        "选择要清空的 R2 桶",
        [
            MenuChoice("public", "清空 R2_PUBLIC_BUCKET"),
            MenuChoice("private", "清空 R2_PRIVATE_BUCKET"),
            MenuChoice("both", "清空 R2_PUBLIC_BUCKET 和 R2_PRIVATE_BUCKET"),
        ],
        allow_back=True,
    )
    if selected == "__back__":
        return
    target_label = {
        "public": "R2_PUBLIC_BUCKET",
        "private": "R2_PRIVATE_BUCKET",
        "both": "R2_PUBLIC_BUCKET + R2_PRIVATE_BUCKET",
    }.get(selected, selected)
    plan = ExecutionPlan(
        entry_key="clear_r2_bucket",
        argv=[],
        base_command=CLEAR_R2_BASE_COMMAND,
        success_prefix="清空完成，退出码: ",
        cancel_message="已取消清空 R2 桶。",
    )
    backend.write(f"清空目标: {target_label}")
    if not backend.confirm("确认执行清空操作？", default=False):
        backend.write(plan.cancel_message)
        return
    _run_with_clear_target(backend, plan, selected)


def _handle_delete_run(backend: QuestionaryMenuBackend) -> None:
    from scripts.r2_upload.delete_run import list_remote_runs

    try:
        run_names = list_remote_runs()
    except Exception as exc:
        backend.write(f"无法获取远端 run 列表: {exc}")
        return

    if not run_names:
        backend.write("数据库中未找到任何 run 记录。")
        return

    selected = backend.select(
        "选择要删除的 Run",
        [MenuChoice(name, name) for name in run_names],
        allow_back=True,
    )
    if selected == "__back__":
        return

    plan = ExecutionPlan(
        entry_key="delete_run",
        argv=["--run-dir", selected],
        base_command=f"{DELETE_RUN_BASE_COMMAND} {selected}",
        success_prefix="删除完成，退出码: ",
        cancel_message="已取消删除操作。",
    )
    backend.write(f"准备删除 run: {selected}")
    backend.write(f"  - R2: runs/{selected}/ 前缀下所有对象")
    backend.write("  - 数据库: runs 表记录及全部关联数据（级联删除）")
    if not backend.confirm("确认执行删除操作？", default=False):
        backend.write(plan.cancel_message)
        return
    _run_execution_plan(backend, plan)


def _confirm_and_execute(
    backend: QuestionaryMenuBackend,
    plan: ExecutionPlan,
) -> None:
    backend.write(f"预览命令: {plan.preview_command}")
    if not backend.confirm("确认执行？", default=True):
        backend.write(plan.cancel_message)
        return
    _run_execution_plan(backend, plan)


def _run_with_clear_target(
    backend: QuestionaryMenuBackend,
    plan: ExecutionPlan,
    clear_target: str,
) -> None:
    entry = get_entry(plan.entry_key)
    main_func = load_entrypoint(entry)
    original_target = os.environ.get("SDSLAB_R2_CLEAR_BUCKET_TARGET")
    original_legacy_target = os.environ.get("SDSLAB_R2_CLEAR_BUCKET_NAME")
    os.environ["SDSLAB_R2_CLEAR_BUCKET_TARGET"] = clear_target
    _ = os.environ.pop("SDSLAB_R2_CLEAR_BUCKET_NAME", None)
    try:
        exit_code = _execute_main(main_func, [])
    finally:
        if original_target is None:
            _ = os.environ.pop("SDSLAB_R2_CLEAR_BUCKET_TARGET", None)
        else:
            os.environ["SDSLAB_R2_CLEAR_BUCKET_TARGET"] = original_target
        if original_legacy_target is None:
            _ = os.environ.pop("SDSLAB_R2_CLEAR_BUCKET_NAME", None)
        else:
            os.environ["SDSLAB_R2_CLEAR_BUCKET_NAME"] = original_legacy_target
    backend.write(f"{plan.success_prefix}{exit_code}")


def _run_execution_plan(backend: QuestionaryMenuBackend, plan: ExecutionPlan) -> None:
    entry = get_entry(plan.entry_key)
    main_func = load_entrypoint(entry)
    exit_code = _execute_main(main_func, plan.argv)
    backend.write(f"{plan.success_prefix}{exit_code}")


def _execute_main(main_func: ScriptMain, argv: list[str] | None) -> int:
    try:
        result = main_func(argv)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else 1
    return result if isinstance(result, int) else 1


def _prompt_generate_advanced_args(backend: QuestionaryMenuBackend) -> list[str]:
    defaults = _parser_defaults(build_generate_parser())
    argv: list[str] = []
    if backend.confirm("开启 dry-run？", default=bool(defaults["dry_run"])):
        argv.append("--dry-run")

    run_dir = backend.text("自定义 --run-dir（留空使用默认行为）")
    if run_dir:
        argv.extend(["--run-dir", run_dir])

    if backend.confirm("开启 --retry-failed？", default=False):
        argv.append("--retry-failed")
    if backend.confirm("开启 --retry-incomplete？", default=False):
        argv.append("--retry-incomplete")

    retry_error_code = backend.text("设置 --retry-error-code（逗号分隔，留空跳过）")
    if retry_error_code:
        argv.extend(["--retry-error-code", retry_error_code])

    base_url = backend.text(f"覆盖 --base-url（留空使用默认值 {defaults['base_url']}）")
    if base_url:
        argv.extend(["--base-url", base_url])

    request_timeout = backend.text(
        f"覆盖 --request-timeout-s（留空使用默认值 {defaults['request_timeout_s']}）"
    )
    if request_timeout:
        argv.extend(["--request-timeout-s", request_timeout])

    download_read_timeout = backend.text(
        "覆盖 --download-read-timeout-s"
        f"（留空使用默认值 {defaults['download_read_timeout_s']}）"
    )
    if download_read_timeout:
        argv.extend(["--download-read-timeout-s", download_read_timeout])

    job_timeout = backend.text(
        f"覆盖 --job-timeout-s（留空使用默认值 {defaults['job_timeout_s']}）"
    )
    if job_timeout:
        argv.extend(["--job-timeout-s", job_timeout])

    concurrency = backend.text(
        f"覆盖 --concurrency（留空使用默认值 {defaults['concurrency']}）"
    )
    if concurrency:
        argv.extend(["--concurrency", concurrency])

    download_concurrency = backend.text(
        "覆盖 --download-concurrency"
        f"（留空使用默认值 {defaults['download_concurrency']}）"
    )
    if download_concurrency:
        argv.extend(["--download-concurrency", download_concurrency])

    client_id = backend.text("覆盖 --client-id（留空自动生成）")
    if client_id:
        argv.extend(["--client-id", client_id])
    return argv


def _prompt_generate_novelai_advanced_args(
    backend: QuestionaryMenuBackend,
) -> list[str]:
    argv: list[str] = []
    if backend.confirm("开启 dry-run？", default=False):
        argv.append("--dry-run")

    run_dir = backend.text("自定义 --run-dir（留空使用默认行为）")
    if run_dir:
        argv.extend(["--run-dir", run_dir])

    concurrency = backend.text("覆盖 --concurrency（留空使用默认值 2）")
    if concurrency:
        argv.extend(["--concurrency", concurrency])

    client_id = backend.text("覆盖 --client-id（留空自动生成）")
    if client_id:
        argv.extend(["--client-id", client_id])
    return argv


def _prompt_upload_advanced_args(backend: QuestionaryMenuBackend) -> list[str]:
    defaults = _parser_defaults(build_upload_parser())
    argv: list[str] = []

    run_root = backend.text(f"覆盖 --run-root（留空使用默认值 {defaults['run_root']}）")
    if run_root:
        argv.extend(["--run-root", run_root])

    if backend.confirm("开启 dry-run？", default=bool(defaults["dry_run"])):
        argv.append("--dry-run")

    category = backend.select(
        "选择 --category（或跳过）",
        [
            MenuChoice("", "保持默认"),
            MenuChoice("normal", "normal"),
            MenuChoice("advance", "advance"),
            MenuChoice("nsfw", "nsfw"),
        ],
    )
    if category:
        argv.extend(["--category", category])

    concurrency = backend.text(
        f"覆盖 --concurrency（留空使用默认值 {defaults['concurrency']}）"
    )
    if concurrency:
        argv.extend(["--concurrency", concurrency])

    limit = backend.text("设置 --limit（留空跳过）")
    if limit:
        argv.extend(["--limit", limit])
    return argv


def _list_config_files() -> list[Path]:
    return iter_run_config_files(DATA_MODELS_DIR)


def _is_novelai_config(path: Path) -> bool:
    try:
        import yaml

        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return False
        return (
            data.get("schema_version") == "image-run-config/v2"
            and data.get("backend") == "novelai"
        )
    except Exception:
        return False


def _list_run_dirs(run_root: Path) -> list[Path]:
    if not run_root.exists():
        return []
    return sorted(
        (path for path in run_root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    )


def _default_convert_x_csv() -> str:
    return _default_convert_csv(CONVERT_X_DEFAULT_ENV, DEFAULT_CONVERT_X_CSV)


def _default_convert_y_csv() -> str:
    return _default_convert_csv(CONVERT_Y_DEFAULT_ENV, DEFAULT_CONVERT_Y_CSV)


def _default_annotate_y_yaml() -> str:
    return _default_convert_csv(ANNOTATE_Y_DEFAULT_ENV, DEFAULT_ANNOTATE_Y_YAML)


def _default_convert_csv(env_name: str, fallback_csv: str) -> str:
    configured = os.getenv(env_name)
    if configured is None:
        return fallback_csv
    normalized = configured.strip()
    return normalized or fallback_csv


def _parser_defaults(parser: argparse.ArgumentParser) -> dict[str, object]:
    defaults: dict[str, object] = {}
    for action in parser._actions:
        if action.dest == "help":
            continue
        defaults[action.dest] = action.default
    return defaults
