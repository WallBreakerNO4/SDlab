# Agent Guide (sd-style-lab/images-script)

**生成时间:** 2026-02-17T17:53:02+0800
**Commit:** 94e9de9
**分支:** master

本文件面向在本仓库里自动写代码/改代码的 agent；子目录的 `AGENTS.md` 只覆盖该目录的“局部知识”，避免与根文件重复。

## 概览

- 目标：用 ComfyUI 遍历 X/Y prompt 网格生图；落盘 `run.json` + `metadata.jsonl` + `images/`
- 栈：Python `>=3.13`（本仓库默认 `3.14`，见 `.python-version`）；依赖用 `uv`（`uv.lock` 已提交）；测试 `pytest`

## 结构

```text
./
├── main.py
├── scripts/                 # 核心实现（CLI runner / ComfyUI client / workflow patch / prompt grid）
│   └── AGENTS.md
├── tests/                   # pytest（偏“可观测输出”）
│   └── AGENTS.md
├── data/                    # 输入 CSV 与 ComfyUI workflow JSON（只读资产）
│   └── AGENTS.md
├── comfyui_api_outputs/     # 运行输出（生成物；已在 .gitignore）
├── pyproject.toml
└── uv.lock
```

## 去哪儿改

| 任务 | 位置 |
| --- | --- |
| 顶层入口（只做委托） | `main.py` |
| CLI 参数/运行逻辑（dry-run/断点续跑/落盘） | `scripts/comfyui_part1_generate.py` |
| ComfyUI HTTP/WS 与结构化错误 | `scripts/comfyui_client.py` |
| workflow 注入与引用追溯 | `scripts/workflow_patch.py` |
| prompt 组合/hash/seed 派生 | `scripts/prompt_grid.py` |
| 测试 | `tests/` |

## 常用命令

```bash
uv sync
uv sync --no-dev
uv sync --frozen

uv run python main.py --help
uv run python main.py --dry-run --x-csv data/prompts/X/common_prompts.csv --y-csv data/prompts/Y/300_NAI_Styles_Table-test.csv --base-seed 123
uv run python main.py --dry-run --run-dir .sisyphus/evidence/part1-dryrun

uv run pytest -q
uv run pytest -q tests/test_prompt_grid.py
uv run pytest -q -k workflow_patch
```

## 约定（只列项目特有/容易踩坑的）

- 代码主域在 `scripts/`（没有 `src/`）；`main.py` 只是薄包装，委托到 `scripts.comfyui_part1_generate.main()`
- I/O 统一用 `pathlib.Path`；run 产物固定为 `run.json` 与 `metadata.jsonl`（写入细节见 `scripts/AGENTS.md`）
- 错误：远程/WS 失败使用 `ComfyUIClientError`（稳定 `code` + 可序列化 `context`；message 保持短）
- 类型：倾向全量标注；需要时用 `typing.cast(...)` 表达意图，避免吞类型
- 本仓库未固定 ruff/black/isort/mypy/pyright 全局配置；不要据此引入新的强制风格/依赖

## 边界 / 反模式

- 不改/不提交：`.env`、`.venv/`、`__pycache__/`、`comfyui_api_outputs/`（生成物；扫描/搜索时优先排除）
- 不要在修 bug 时顺手大重构；单测失败不要“删测/放宽断言”来过
- 新增依赖或修改 `pyproject.toml`：除非用户明确要求，否则先停下来问

## 分层文档

- `scripts/AGENTS.md`：脚本层 code map、错误/落盘合约、pyright 约定
- `tests/AGENTS.md`：测试结构、fixture/断言形态、mock 约定
- `data/AGENTS.md`：CSV/workflow 资产说明（字段与用途）
