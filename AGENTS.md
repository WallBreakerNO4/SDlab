# Agent Guide (sd-style-lab/images-script)

**生成时间:** 2026-03-17T18:54:57+08:00
**Commit:** ce7f591
**分支:** refactor/scripts
本文件给仓库级 agent 使用；子目录 `AGENTS.md` 只补充局部知识，不重复根规则。

## 概览

- 仓库分两条主线：Next.js 站点负责展示 runs / grid / 图片；Python 脚本负责生图、上传 R2、写入 Supabase。
- 当前网站数据链路以 Supabase + R2 为准；不要假设 Web 侧仍有本地文件降级读取。
- 认证链路走 Supabase SSR：浏览器端 `lib/supabase-browser.ts`，服务端 `lib/supabase-auth.ts`，会话刷新在 `middleware.ts`。
- Web 部署目标是 OpenNext + Cloudflare：本地 `next dev` 会启 Miniflare，部分服务端能力通过 Workers bindings 读取。

## 结构

```text
./
├── app/                    # App Router 页面与 API route
│   ├── api/comfyui/        # runs/run/grid/row + workflow 下载
│   ├── api/r2/private/     # R2 私有对象代理
│   └── auth/               # Supabase PKCE callback
├── components/             # 业务组件 + UI primitives + auth provider
│   ├── comfyui/            # 虚拟网格/图片预览/blurhash
│   └── ui/                 # shadcn/radix primitives
├── lib/                    # Supabase/R2/路径安全/共享类型
├── scripts/                # Python 生图、上传、CLI、辅助转换
│   ├── generation/         # 核心 runner + ComfyUI 客户端
│   ├── r2_upload/          # R2 上传 + Supabase 写入
│   ├── cli/                # 交互菜单与入口注册
│   └── other/              # CSV/YAML 资产转换工具
├── tests/                  # pytest（合约与可观测输出）
├── e2e/                    # Playwright 端到端
├── supabase/               # 本地配置与迁移
├── data/                   # 只读输入资产（prompt/workflow/run config）
├── hooks/                  # 共享前端行为
├── types/                  # Next 生成类型（只读）
├── middleware.ts           # Supabase session refresh
└── main.py                 # Python 顶层入口（委托到 scripts）
```

## 去哪儿看

| 任务                  | 位置                                                                             | 备注                                            |
| --------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------- |
| Python 顶层入口       | `main.py`                                                                        | 菜单/主 runner 的统一入口                       |
| 生图主入口            | `scripts/generation/comfyui_part1_generate.py`                                   | dry-run / retry / 落盘合约                      |
| 生图配置加载          | `scripts/generation/runner_config.py`                                            | `--config` YAML schema + repo-relative 资产校验 |
| 并发 runner           | `scripts/generation/runner_coordinator.py`                                       | ThreadPoolExecutor 双池                         |
| ComfyUI 通信          | `scripts/generation/comfyui_client.py`                                           | HTTP / WS / 错误码                              |
| R2 上传入口           | `scripts/r2_upload/upload_images_to_r2.py`                                       | 编码、上传、写 Supabase                         |
| 上传规划              | `scripts/r2_upload/upload_planner.py`                                            | 多变体规划 + 并发编码                           |
| 资产转换脚本          | `scripts/other/convert_*.py`                                                     | 文件名遗留 `json`，实际输出 YAML 资产           |
| run 配置示例          | `data/runs/example.yaml`                                                         | `image-run-config/v1` 示例                      |
| 网站首页              | `app/page.tsx`                                                                   | 读取 runs 列表                                  |
| run 详情页            | `app/runs/[runDir]/page.tsx`                                                     | 并行拉 run + grid，显示 workflow 下载入口       |
| App API 总约定        | `app/api/AGENTS.md`                                                              | `app/api/**/route.ts` 共享约束                  |
| ComfyUI API           | `app/api/comfyui/**/route.ts`                                                    | Node runtime + Supabase 查询 + workflow 下载    |
| R2 私有代理           | `app/api/r2/private/[...r2Key]/route.ts`                                         | 认证后代理 R2 private bucket                    |
| Auth 回调特例         | `app/auth/AGENTS.md`                                                             | PKCE callback 直接交换 session                  |
| 站点壳层 / 登录入口   | `app/layout.tsx`、`components/site-header.tsx`                                   | ThemeProvider + AuthProvider + 登录弹窗入口     |
| Cloudflare / OpenNext | `next.config.ts`、`open-next.config.ts`、`cloudflare-env.d.ts`、`wrangler.jsonc` | 本地 Miniflare + Workers bindings / vars        |
| 服务端 Supabase       | `lib/supabase-auth.ts`                                                           | `server-only` + cookie session                  |
| 浏览器端 Supabase     | `lib/supabase-browser.ts`                                                        | AuthProvider 使用                               |
| runDir 校验           | `lib/comfyui-types.ts`                                                           | API 侧 `isValidRunDir()` type guard             |
| 路径安全              | `lib/comfyui-path.ts`                                                            | 共享路径工具与相对路径逃逸防护                  |
| R2 URL 构建           | `lib/r2-url.ts`                                                                  | 公开/私有 URL 与变体白名单                      |
| 会话刷新              | `middleware.ts`                                                                  | Edge middleware，不能引 `lib/supabase-auth.ts`  |

## 代码图

| 符号                          | 类型     | 位置                                           | 角色                |
| ----------------------------- | -------- | ---------------------------------------------- | ------------------- |
| `main`                        | function | `main.py`                                      | Python CLI 总入口   |
| `run`                         | function | `scripts/generation/comfyui_part1_generate.py` | 生图主流程          |
| `run_retry`                   | function | `scripts/generation/comfyui_part1_generate.py` | retry / replay 入口 |
| `GET`                         | function | `app/api/comfyui/runs/route.ts`                | runs 列表 API       |
| `GET`                         | function | `app/api/comfyui/run/[runDir]/route.ts`        | run 详情 API        |
| `GET`                         | function | `app/api/comfyui/run/[runDir]/grid/route.ts`   | grid + blurhash API |
| `GET`                         | function | `app/api/comfyui/run/[runDir]/row/route.ts`    | 行级图片 API        |
| `publicObjectUrl`             | function | `lib/r2-url.ts`                                | 公开变体 URL        |
| `privateObjectUrl`            | function | `lib/r2-url.ts`                                | 私有代理 URL        |
| `isValidRunDir`               | function | `lib/comfyui-types.ts`                         | runDir 形态校验     |
| `assertSafeRelativeImagePath` | function | `lib/comfyui-path.ts`                          | 相对图片路径校验    |

## 约定（项目特有）

- 语言边界：Node/Next 不直接调用 Python；网站只消费 Supabase + R2，不读取 Python 内部实现。
- Python：I/O 统一 `pathlib.Path`；生图产物固定为 `run.json` + `metadata.jsonl` + `images/`；写盘后保持 flush/fsync 语义。
- API：`app/api/**/route.ts` 保持 `runtime = "nodejs"`；错误响应返回固定短文案，不透出绝对路径、stack、凭证。
- Supabase：ComfyUI API 与 R2 私有代理统一用 `createSupabaseAuthClient()`；浏览器端认证统一用 `createSupabaseBrowserClient()`；`app/auth/callback/route.ts` 为 PKCE 交换 session 的例外。
- Middleware 例外：`middleware.ts` 不能 import `lib/supabase-auth.ts`，因为后者依赖 `server-only` + `next/headers`。
- Cloudflare：本地 `next dev` 通过 `initOpenNextCloudflareForDev()` 提供 Miniflare 绑定；服务端访问 R2 bucket 走 `getCloudflareContext()`。
- 路径与 URL：API 入口的 `runDir` 先用 `lib/comfyui-types.ts:isValidRunDir()` 判形态；共享路径处理再走 `lib/comfyui-path.ts`；R2 URL 统一走 `lib/r2-url.ts`。
- 前端：大网格必须虚拟化；图片优先消费 R2 display/thumb 变体并配合 blurhash 占位。
- 工具链：Python 用 `uv` + `pytest`（>=3.13）；Web 用 `pnpm` + Next 16 + React 19；E2E 用 Playwright。
- Supabase CLI：本仓库统一使用 `pnpm dlx supabase ...`，不要混用 `npx supabase ...`。
- 协作文档与 git commit message 默认使用中文；涉及环境变量示例时优先更新 `.env.example`，不要直接读取/修改真实 `.env`。

## 反模式

- 不改/不提交：真实环境文件（如 `.env` / `.env.local` / 其他私密配置）、`.venv/`、`node_modules/`、`.next/`、`.open-next/`、`comfyui_api_outputs/`、`.sisyphus/`。
- 不要把运行输出写进 `data/`；`data/` 只放可复现输入资产。
- 不要手改 `types/routes.d.ts`、`types/validator.ts` 等 Next 生成文件。
- 不要在页面/组件/route 中绕过 `lib/comfyui-path.ts` 或 `lib/r2-url.ts` 直接拼路径。
- 不要把 ComfyUI 整段响应、R2 key 细节、Supabase 凭证写进错误消息或日志。
- 修 bug 不要顺手大重构；测试失败不要删测或放宽断言来过。
- 未经用户明确要求，不修改 `package.json` / `pyproject.toml` 增加依赖。
- 不要把 `comfyui_api_outputs/`、`.next/`、`.open-next/`、`dist/`、`build/`、`.pytest_cache/`、`.ruff_cache/`、`.wrangler/`、`supabase/.temp/` 之类生成/缓存目录当源码或层级打分依据。

## 常用命令

```bash
# Python
uv sync
uv sync --no-dev
uv run python main.py --help
uv run python main.py --config data/runs/example.yaml
uv run python main.py --config data/runs/example.yaml --dry-run
uv run pytest -q
uv run pytest -q tests/test_prompt_grid.py

# R2 上传
uv run python -m scripts.r2_upload.upload_images_to_r2 --help
uv run python -m scripts.r2_upload.upload_images_to_r2 --dry-run --run-dir comfyui_api_outputs/run-xxx

# Web
pnpm dev
pnpm build
pnpm start
pnpm lint

# E2E / Supabase
pnpm test:e2e
E2E_SERVER=start E2E_PORT=3001 pnpm test:e2e -- -g "task 13"
pnpm dlx supabase start
pnpm dlx supabase db reset
pnpm dlx supabase migration new <name>
```

## 分层文档

- `app/AGENTS.md`：App Router 页面与 API 的局部规则。
- `app/api/AGENTS.md`：`app/api/**/route.ts` 共性约定。
- `app/api/comfyui/AGENTS.md`：ComfyUI 查询 / workflow 下载 API 约定。
- `app/api/r2/AGENTS.md`：R2 私有对象代理、鉴权与 range/HEAD 约定。
- `app/auth/AGENTS.md`：Supabase PKCE callback 的局部特例。
- `components/AGENTS.md` / `components/ui/AGENTS.md` / `components/comfyui/AGENTS.md`：组件分层、UI primitives、网格性能约定。
- `lib/AGENTS.md`：Supabase/R2/路径安全/共享类型边界。
- `scripts/AGENTS.md` / `scripts/generation/AGENTS.md` / `scripts/r2_upload/AGENTS.md` / `scripts/cli/AGENTS.md` / `scripts/other/AGENTS.md`：Python 主代码域。
- `tests/AGENTS.md`、`e2e/AGENTS.md`、`supabase/AGENTS.md`、`data/AGENTS.md`、`hooks/AGENTS.md`、`types/AGENTS.md`：各自目录局部规则。
