# Agent Guide (sd-style-lab/images-script)

**生成时间:** 2026-02-19T03:47:25+0800
**Commit:** 370756d
**分支:** master

本文件面向在本仓库里自动写代码/改代码的 agent；子目录的 `AGENTS.md` 只覆盖该目录的“局部知识”，避免与根文件重复。

## 概览

- 这个仓库包含两部分：展示用的网站（Next.js）+ 生图用的脚本（Python/ComfyUI）
- 生图脚本：遍历 X/Y prompt 网格；落盘 `run.json` + `metadata.jsonl` + `images/`
- 网站：读取 `comfyui_api_outputs/` 下的 run 产物并展示 runs/grid/image；E2E 用 Playwright

## 结构

```text
./
├── app/                      # Next.js App Router（页面 + /api/comfyui/* 读取 run 产物）
│   ├── AGENTS.md
│   └── api/comfyui/           # Node API：runs/run/grid/image（路径安全 + payload 约定）
│       └── AGENTS.md
├── components/               # 业务组件（ComfyUI 预览/虚拟网格等）
│   ├── ui/                   # shadcn/radix 基础组件（体量大，约定集中）
│   │   └── AGENTS.md
│   ├── comfyui/               # ComfyUI 领域组件（网格/预览等）
│   │   └── AGENTS.md
│   └── AGENTS.md
├── lib/                      # Node 侧读取 run.json/metadata.jsonl + 路径安全
│   └── AGENTS.md
├── e2e/                      # Playwright 端到端测试
│   └── AGENTS.md
├── types/                    # Next.js 生成类型（不要手改）
│   └── AGENTS.md
├── main.py                   # Python 程序入口（只做委托）
├── scripts/                  # 生图脚本核心实现
│   └── AGENTS.md
├── tests/                    # pytest（偏“可观测输出”）
│   └── AGENTS.md
├── data/                     # 输入资产（CSV + workflow JSON；只读）
│   └── AGENTS.md
├── comfyui_api_outputs/      # 运行输出（生成物；已在 .gitignore；网站只读消费）
├── package.json              # Next.js/ESLint/Playwright
├── pyproject.toml            # Python deps（uv）
└── uv.lock
```

## 复杂度分级（用于 AGENTS 布局）

| 目录 | 复杂度(0-20) | 理由 |
| --- | ---: | --- |
| `scripts/` | 20 | CLI runner + 并发 + 落盘合约（`run.json`/`metadata.jsonl`/images） |
| `components/ui/` | 18 | primitives 体量大；`cva`/`cn()`/Radix 约定集中（含 `sidebar.tsx`） |
| `lib/` | 14 | 解析 run 产物 + 路径安全（API/页面都依赖） |
| `app/api/comfyui/` | 12 | Node runtime + allowlist + payload 收敛 + 安全回归 |
| `components/comfyui/` | 10 | 业务核心（虚拟滚动网格 + 预览交互） |
| `e2e/` | 10 | Playwright 回归（安全/性能/虚拟滚动） |
| `tests/` | 9 | pytest 合约测试（结构化错误/落盘/纯函数） |

## 去哪儿改

| 任务 | 位置 | 备注 |
| --- | --- | --- |
| 顶层 Python 入口（只做委托） | `main.py` | 调 `scripts.generation.comfyui_part1_generate.main()` |
| CLI 参数/运行逻辑（dry-run/断点续跑/落盘） | `scripts/generation/comfyui_part1_generate.py` | 产物：`run.json`/`metadata.jsonl`/`images/` |
| ComfyUI HTTP/WS 与结构化错误 | `scripts/generation/comfyui_client.py` | `ComfyUIClientError`（`code`+`context`） |
| workflow 注入与引用追溯 | `scripts/generation/workflow_patch.py` | 追溯 KSampler 引用链 |
| prompt 组合/hash/seed 派生 | `scripts/generation/prompt_grid.py` | 纯函数优先 |
| 网站首页（runs 列表） | `app/page.tsx` | 拉 `/api/comfyui/runs` |
| run 详情页（grid + 预览） | `app/runs/[runDir]/page.tsx` | 拉 `/api/comfyui/run/*` |
| API：runs/run/grid/image | `app/api/comfyui/**/route.ts` | `runtime = "nodejs"` |
| 读取 run 产物（Node） | `lib/comfyui-fs.ts` | 解析 `run.json`/`metadata.jsonl` |
| 路径/遍历防护（Node） | `lib/comfyui-path.ts` | runDir allowlist + imagePath 安全规则 |
| UI 基础组件（shadcn） | `components/ui/` | `cva` + `cn()` + Radix |
| 业务网格组件 | `components/comfyui/virtual-grid.tsx` | 虚拟滚动 + 图片预览 |
| E2E | `e2e/` | Playwright；产物写 `.sisyphus/evidence/` |

## 常用命令

```bash
# Python（生图脚本）
uv sync
uv sync --no-dev
uv sync --frozen

uv run python main.py --help
uv run python main.py --dry-run --x-json data/prompts/X/common_prompts.json --y-json data/prompts/Y/300_NAI_Styles_Table-test.json --base-seed 123
uv run python main.py --dry-run --run-dir .sisyphus/evidence/part1-dryrun

uv run pytest -q
uv run pytest -q tests/test_prompt_grid.py
uv run pytest -q -k workflow_patch

# Website（Next.js）
pnpm dev
pnpm build
pnpm start
pnpm lint

# E2E（Playwright）
pnpm test:e2e
E2E_SERVER=start E2E_PORT=3001 pnpm test:e2e -- -g "task 16"
```

## 约定（只列项目特有/容易踩坑的）

- 边界：Node/Next 不调用 Python 代码；网站通过 `lib/comfyui-fs.ts` 读取 `comfyui_api_outputs/` 的产物
- Python：I/O 统一用 `pathlib.Path`；产物固定为 `run.json` + `metadata.jsonl`（写入细节见 `scripts/AGENTS.md`）
- Node：所有 `runDir`/`imagePath` 必须经过 `lib/comfyui-path.ts` 校验；API 错误响应避免泄露绝对路径/stack
- 工具链：Python 用 uv/pytest；Web 用 pnpm/Next/ESLint；E2E 用 Playwright（输出写 `.sisyphus/evidence/playwright/`）

## 边界 / 反模式

- 不改/不提交：`.env*`、`.venv/`、`node_modules/`、`.next/`、`comfyui_api_outputs/`、`.sisyphus/`（均为环境/生成物）
- 不要把运行输出（`run.json`/`metadata.jsonl`/图片）写进 `data/`（`data/` 只读资产）
- `types/routes.d.ts`、`types/validator.ts` 为 Next.js 生成文件（文件头已写明），不要手改
- 修 bug 不要顺手大重构；单测失败不要“删测/放宽断言”来过
- 新增依赖或修改 `pyproject.toml`/`package.json`：除非用户明确要求，否则先停下来问

## 分层文档

- `app/AGENTS.md`：App Router 页面与 /api/comfyui 路由约定
- `app/api/comfyui/AGENTS.md`：ComfyUI API 细则（runtime/校验顺序/payload/错误映射）
- `components/AGENTS.md`：业务组件目录分工；`components/ui/` 见独立文档
- `components/ui/AGENTS.md`：shadcn/radix 组件模式（cva/variants/cn）
- `components/comfyui/AGENTS.md`：ComfyUI 领域组件（VirtualGrid 的性能/交互/图片路径约定）
- `lib/AGENTS.md`：读取 run 产物与路径安全
- `e2e/AGENTS.md`：Playwright 约定、环境变量与证据落盘
- `types/AGENTS.md`：Next 生成类型的边界
- `scripts/AGENTS.md`：生图脚本层 code map、错误/落盘合约、pyright 约定
- `tests/AGENTS.md`：pytest 结构、fixture/断言形态、mock 约定
- `data/AGENTS.md`：CSV/workflow 资产说明（字段与用途）
