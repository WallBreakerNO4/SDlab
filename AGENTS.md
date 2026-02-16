# Agent Guide (sd-style-lab/images-script)

本文件面向在本仓库里自动写代码/改代码的 agent。

## 1) 项目概览

- 语言：Python（`pyproject.toml` 要求 `>=3.13`；本仓库默认 `3.14`，见 `.python-version`）
- 依赖管理：uv（`uv.lock` 已提交）
- 程序入口：`main.py`（薄包装，委托到 `scripts/comfyui_part1_generate.py`）
- 核心模块：
  - `scripts/comfyui_part1_generate.py`：CLI/运行器（dry-run、断点续跑、落盘 run.json + metadata.jsonl）
  - `scripts/comfyui_client.py`：ComfyUI HTTP/WS 客户端 + 结构化错误
  - `scripts/workflow_patch.py`：workflow JSON 注入（CLIPTextEncode + 引用追溯）
  - `scripts/prompt_grid.py`：CSV 读取与 prompt 组合、hash、seed 派生
- 测试：pytest（`tests/`）

## 2) 常用命令（Build/Lint/Test）

### 环境/依赖

```bash
# 安装/同步依赖（默认包含 dev 依赖组）
uv sync

# 只要运行时依赖（不装 dev 依赖组）
uv sync --no-dev

# 锁定/冻结（CI/复现用）
uv sync --frozen
```

### 运行脚本（本地）

```bash
# 查看 CLI 帮助
uv run python main.py --help

# dry-run（不连 ComfyUI；仍会写 run.json + metadata.jsonl）
uv run python main.py --dry-run \
  --x-csv data/prompts/X/common_prompts.csv \
  --y-csv data/prompts/Y/300_NAI_Styles_Table-test.csv \
  --base-seed 123

# 指定 run 目录（便于验收/调试）
uv run python main.py --dry-run --run-dir .sisyphus/evidence/part1-dryrun
```

### 测试（推荐用 uv 运行）

```bash
# 全量测试
uv run pytest -q

# 只跑某个文件
uv run pytest -q tests/test_prompt_grid.py

# 只跑单个用例（最常用）
uv run pytest -q tests/test_prompt_grid.py::test_compute_prompt_hash_uses_normalized_prompt_sha256_hex

# 用 -k 过滤（子串/表达式）
uv run pytest -q -k workflow_patch
```

### Lint/Format/Type

- 本仓库当前没有固定的 ruff/black/isort/mypy/pyright 配置（见 `pyproject.toml`）。
- 代码里存在 `# pyright:` 文件级指令与少量 `pyright: ignore[...]`（如 `scripts/comfyui_client.py`）。
- 若你的环境装了相关工具，可以作为“辅助信号”运行，但不要据此引入新的强制风格/依赖。

## 3) 代码风格（以现有代码为准）

### 导入（imports）

- 优先使用：`from __future__ import annotations`（现有核心模块使用：`scripts/comfyui_part1_generate.py`、`scripts/comfyui_client.py`）。
- 导入分组顺序：标准库 → 第三方 → 本地模块；组间空行。
- 若脚本需要在“直接执行文件”场景下修正 `sys.path`：先处理路径，再导入本地模块，并用 `# noqa: E402` 标注（示例：`scripts/comfyui_part1_generate.py`）。

### 格式化（formatting）

- 4 空格缩进；保持现有的 black-ish 换行与 trailing comma 风格（仓库未固定 formatter，但现有代码整体一致）。
- 字符串多用双引号；写文件时明确 `encoding="utf-8"`。

### 类型（types）

- 全面类型标注：参数、返回值、关键局部变量（示例：`scripts/comfyui_client.py`、`scripts/workflow_patch.py`、`tests/`）。
- 使用 Python 3.13+ 语法：`list[str]`、`dict[str, object]`、`str | None`。
- 避免“吞类型”的写法；必要时用 `typing.cast(...)` 并解释为什么（示例：`scripts/comfyui_part1_generate.py`）。

### 命名（naming）

- 函数/变量：`snake_case`；类/异常：`PascalCase`；常量：`UPPER_SNAKE_CASE`。
- 测试：文件 `tests/test_*.py`；用例函数 `test_*`。

### 数据与 I/O

- 路径统一用 `pathlib.Path`；读写用 `Path.open(..., encoding="utf-8")` 或 `Path.read_text/write_text`。
- JSON：
  - `run.json` 使用 `json.dumps(..., ensure_ascii=False, indent=2)`（示例：`scripts/comfyui_part1_generate.py`）。
  - `metadata.jsonl` 一行一个 JSON；写入后 `flush + fsync`（示例：`scripts/comfyui_part1_generate.py`）。

## 4) 错误处理与日志

- CLI 参数/配置校验：抛 `ValueError`；入口捕获后打印到 stderr，并返回退出码 `2`（示例：`scripts/comfyui_part1_generate.py`、`main.py`）。
- 运行中单个 cell 失败：记录 `LOG.exception(...)`，并把结构化 error 写入 `metadata.jsonl`；总体退出码：
  - 全 success/skipped：`0`
  - 任一 failed：`1`
- 远程请求/WS 失败：使用 `ComfyUIClientError` 层级（`scripts/comfyui_client.py`），并携带：
  - `code`: 稳定错误码
  - `context`: 可序列化上下文（不要塞超大对象/敏感信息）
- 错误信息保持简短；细节进 `context`（测试里对 message 长度与内容有约束，见 `tests/test_comfyui_client.py`）。

日志约定：

- `LOG = logging.getLogger(__name__)`；`_configure_logging()` 只在 root logger 没 handler 时调用 `basicConfig`。
- 与 tqdm 共存：用 `tqdm.contrib.logging.logging_redirect_tqdm` 包裹运行循环。

## 5) 测试约定（pytest）

- 使用内建 fixtures：`tmp_path`、`monkeypatch`、`capsys`；异常断言用 `pytest.raises`。
- 测试更偏“可观测输出”：文件是否生成、JSON 字段是否符合合约（示例：`tests/test_runner_dry_run.py`、`tests/test_main_entrypoint.py`）。

单测定位小抄：

```bash
# 先跑相关子集，再跑全量
uv run pytest -q -k comfyui_client
uv run pytest -q
```

## 6) Cursor / Copilot 规则

- 未发现 Cursor 规则：`.cursor/rules/`、`.cursorrules` 不存在。
- 未发现 Copilot 指令：`.github/copilot-instructions.md` 不存在。

## 7) 约束与踩坑

- 不要把 `.env` 提交进 git（已在 `.gitignore`；参考 `.env.example`）。
- 不要把 `.venv/`、`.ruff_cache/` 等产物当作源码修改目标。
- 仓库不是 bun/npm 项目；验证以 `uv run pytest -q` 为准（见 `.sisyphus/notepads/.../issues.md`）。
