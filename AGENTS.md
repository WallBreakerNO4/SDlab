# Agent Guide (sd-style-lab/images-script)

**生成时间:** 2026-02-28T22:25:00+0800
**Commit:** 1d29da6
**分支:** feat/website-r2-images

本文件面向在本仓库里自动写代码/改代码的 agent；子目录的 `AGENTS.md` 只覆盖该目录的"局部知识"，避免与根文件重复。

## 概览

- 这个仓库包含两部分：展示用的网站（Next.js）+ 生图用的脚本（Python/ComfyUI）
- 生图脚本：遍历 X/Y prompt 网格；落盘 `run.json` + `metadata.jsonl` + `images/`
- 上传脚本：将生成图片编码为多变体（webp/avif）上传 R2 + 写入 Supabase 索引
- 网站：从 Supabase 读取 run 数据，通过 R2 公开/私有链接展示图片；E2E 用 Playwright

## 结构

```text
./
├── app/                      # Next.js App Router（页面 + API routes）
│   ├── AGENTS.md
│   ├── api/comfyui/           # run/grid/image API（数据源已迁移到 Supabase）
│   │   └── AGENTS.md
│   └── api/r2/                # R2 私有图片代理（aws4fetch 签名转发）
├── components/               # 业务组件（ComfyUI 预览/虚拟网格等）
│   ├── ui/                   # shadcn/radix 基础组件（体量大，约定集中）
│   │   └── AGENTS.md
│   ├── comfyui/               # ComfyUI 领域组件（网格/预览/blurhash）
│   │   └── AGENTS.md
│   └── AGENTS.md
├── lib/                      # Node 侧数据层（Supabase 客户端 + R2 URL + 路径安全）
│   └── AGENTS.md
├── e2e/                      # Playwright 端到端测试
│   └── AGENTS.md
├── types/                    # Next.js 生成类型（不要手改）
│   └── AGENTS.md
├── supabase/                 # Supabase 本地开发配置与迁移
│   └── AGENTS.md
├── main.py                   # Python 程序入口（只做委托）
├── scripts/                  # 生图脚本 + R2 上传脚本
│   └── AGENTS.md
│   ├── cli/                  # 交互菜单与脚本入口注册
│   │   └── AGENTS.md
│   ├── generation/           # 核心 runner + ComfyUI 通信 + workflow patch
│   │   └── AGENTS.md
│   ├── other/                # CSV 转 JSON 的辅助转换脚本
│   └── r2_upload/            # R2 上传 + Supabase 写入（已实现）
│       └── AGENTS.md
├── tests/                    # pytest（偏"可观测输出"）
│   └── AGENTS.md
├── data/                     # 输入资产（CSV + workflow JSON；只读）
│   └── AGENTS.md
├── hooks/                    # 前端复用 hooks（当前规模小）
│   └── AGENTS.md
├── public/                   # Next.js 静态资源（无独立约定）
├── documents/                # 设计/部署文档（R2+Supabase 等）
├── comfyui_api_outputs/      # 运行输出（生成物；已在 .gitignore；本地调试用）
├── package.json              # Next.js/ESLint/Playwright
├── pyproject.toml            # Python deps（uv, >=3.13）
└── uv.lock
```

## 复杂度分级（用于 AGENTS 布局）

| 目录 | 复杂度(0-20) | 理由 |
| --- | ---: | --- |
| `scripts/` | 20 | CLI runner + 并发 + 落盘合约 + R2 上传完整实现 |
| `scripts/generation/` | 18 | 核心 runner（已拆分 coordinator/env/selection/payload/records 等 15+ 文件） |
| `scripts/r2_upload/` | 18 | R2 客户端 + Supabase 写入 + 编码变体 + 上传规划（19 Python 文件） |
| `components/ui/` | 18 | primitives 体量大；`cva`/`cn()`/Radix 约定集中（含 `sidebar.tsx`） |
| `lib/` | 16 | Supabase 客户端 + R2 URL 构建 + ComfyUI 产物解析 + 路径安全 |
| `tests/` | 14 | 37 个测试文件覆盖 generation/r2_upload/cli/retry/合约 |
| `app/api/comfyui/` | 12 | Node runtime + Supabase 查询 + payload 收敛 + 安全回归 |
| `components/comfyui/` | 12 | 虚拟滚动网格 + blurhash 占位 + grid-image + 预览交互 |
| `e2e/` | 10 | Playwright 回归（冒烟/主流程/R2 图片源） |
| `scripts/cli/` | 8 | 交互入口层（菜单、入口点注册、执行守卫） |
| `hooks/` | 4 | 共享前端行为（当前体量小） |

## 去哪儿改

| 任务 | 位置 | 备注 |
| --- | --- | --- |
| 顶层 Python 入口（只做委托） | `main.py` | 调 `scripts.generation.comfyui_part1_generate.main()` |
| CLI 参数/运行逻辑（dry-run/断点续跑/落盘） | `scripts/generation/comfyui_part1_generate.py` | 产物：`run.json`/`metadata.jsonl`/`images/` |
| 并发 runner 协调 | `scripts/generation/runner_coordinator.py` | ThreadPoolExecutor 提交/下载 |
| ComfyUI HTTP/WS 与结构化错误 | `scripts/generation/comfyui_client.py` | `ComfyUIClientError`（`code`+`context`） |
| workflow 注入与引用追溯 | `scripts/generation/workflow_patch.py` | 追溯 KSampler 引用链 |
| prompt 组合/hash/seed 派生 | `scripts/generation/prompt_grid.py` | 纯函数优先 |
| 交互菜单与入口注册 | `scripts/cli/menu.py`、`scripts/cli/registry.py` | 负责菜单交互、脚本发现、入口分发 |
| R2 上传主入口 | `scripts/r2_upload/upload_images_to_r2.py` | 编码变体 + 并发上传 + Supabase 写入 |
| R2 客户端（S3 兼容） | `scripts/r2_upload/r2_client.py` | boto3 + 重试 + 结构化错误 |
| Supabase 批量写入 | `scripts/r2_upload/supabase_writer.py` | PostgREST upsert + 分批 |
| 上传规划（变体/manifest） | `scripts/r2_upload/upload_planner.py` | 多变体规划 + 并发编码 |
| 网站首页（runs 列表） | `app/page.tsx` | 从 Supabase 拉取 |
| run 详情页（grid + 预览） | `app/runs/[runDir]/page.tsx` | 拉 `/api/comfyui/run/*` |
| API：runs/run/grid/row | `app/api/comfyui/**/route.ts` | `runtime = "nodejs"`；数据源 Supabase |
| API：R2 私有图片代理 | `app/api/r2/private/[...r2Key]/route.ts` | aws4fetch 签名；路径安全校验 |
| Supabase 客户端（Node） | `lib/supabase-server.ts` | service role 客户端；`server-only` |
| R2 URL 构建 | `lib/r2-url.ts` | 公开/私有链接；变体校验 |
| 读取 run 产物（Node，本地降级） | `lib/comfyui-fs.ts` | 解析 `run.json`/`metadata.jsonl` |
| 路径/遍历防护（Node） | `lib/comfyui-path.ts` | runDir allowlist + imagePath 安全规则 |
| UI 基础组件（shadcn） | `components/ui/` | `cva` + `cn()` + Radix |
| 业务网格组件 | `components/comfyui/virtual-grid.tsx` | 虚拟滚动 + R2 图片 + blurhash |
| Blurhash 占位 | `components/comfyui/blurhash-canvas.tsx` | canvas 渲染 blurhash |
| 共享移动端判断 hook | `hooks/use-mobile.ts` | 仅放跨组件可复用行为 |
| Supabase 配置与迁移 | `supabase/` | config.toml + migrations SQL |
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

# R2 上传
uv run python -m scripts.r2_upload.upload_images_to_r2 --help
uv run python -m scripts.r2_upload.upload_images_to_r2 --dry-run --run-dir comfyui_api_outputs/run-xxx

# Website（Next.js）
pnpm dev
pnpm build
pnpm start
pnpm lint

# E2E（Playwright）
pnpm test:e2e
E2E_SERVER=start E2E_PORT=3001 pnpm test:e2e -- -g "task 13"

# Supabase（本地开发）
npx supabase start
npx supabase db reset
npx supabase migration new <name>
```

## 约定（只列项目特有/容易踩坑的）

- 边界：Node/Next 不调用 Python 代码；网站通过 Supabase 读取数据、通过 R2 URL 读取图片
- 本地降级：`lib/comfyui-fs.ts` 仍可从 `comfyui_api_outputs/` 读取本地产物（用于开发/调试）
- Python：I/O 统一用 `pathlib.Path`；产物固定为 `run.json` + `metadata.jsonl`（写入细节见 `scripts/AGENTS.md`）
- Node：所有 `runDir`/`imagePath` 必须经过 `lib/comfyui-path.ts` 校验；R2 key 必须经过 `lib/r2-url.ts` 校验
- API 错误响应避免泄露绝对路径/stack/凭证信息
- 工具链：Python 用 uv/pytest（>=3.13）；Web 用 pnpm/Next/ESLint；E2E 用 Playwright（输出写 `.sisyphus/evidence/playwright/`）

## 边界 / 反模式

- 不改/不提交：`.env*`、`.venv/`、`node_modules/`、`.next/`、`comfyui_api_outputs/`、`.sisyphus/`（均为环境/生成物）
- 不要把运行输出（`run.json`/`metadata.jsonl`/图片）写进 `data/`（`data/` 只读资产）
- `types/routes.d.ts`、`types/validator.ts` 为 Next.js 生成文件（文件头已写明），不要手改
- 修 bug 不要顺手大重构；单测失败不要"删测/放宽断言"来过
- 新增依赖或修改 `pyproject.toml`/`package.json`：除非用户明确要求，否则先停下来问
- 不要把 R2 凭证/Supabase service role key 硬编码到源码中

## 分层文档

- `app/AGENTS.md`：App Router 页面与 API 路由约定（含 R2 代理）
- `app/api/comfyui/AGENTS.md`：ComfyUI API 细则（Supabase 数据源/校验/payload/错误映射）
- `components/AGENTS.md`：业务组件目录分工；`components/ui/` 见独立文档
- `components/ui/AGENTS.md`：shadcn/radix 组件模式（cva/variants/cn）
- `components/comfyui/AGENTS.md`：ComfyUI 领域组件（VirtualGrid/blurhash/grid-image 的性能/交互约定）
- `lib/AGENTS.md`：Supabase 客户端 + R2 URL + ComfyUI 产物解析 + 路径安全
- `e2e/AGENTS.md`：Playwright 约定、环境变量与证据落盘
- `types/AGENTS.md`：Next 生成类型的边界
- `supabase/AGENTS.md`：Supabase 配置/迁移/本地开发约定
- `scripts/AGENTS.md`：生图脚本层 + R2 上传层 code map、错误/落盘合约
- `scripts/generation/AGENTS.md`：核心 runner 实现（coordinator/env/selection/payload 等拆分模块）
- `scripts/cli/AGENTS.md`：交互菜单层（选择、确认、入口加载、异常守卫）
- `scripts/r2_upload/AGENTS.md`：R2 上传实现（客户端/编码/规划/Supabase 写入）
- `tests/AGENTS.md`：pytest 结构、fixture/断言形态、mock 约定
- `data/AGENTS.md`：CSV/workflow 资产说明（字段与用途）
- `hooks/AGENTS.md`：前端 hooks 的职责边界与放置规则
