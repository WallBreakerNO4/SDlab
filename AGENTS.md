<!-- Generated: 2026-04-06 | Updated: 2026-05-19 -->
<!-- Commit: e9e3fdf | 分支: feat/info-page -->

# Agent Guide (sd-style-lab/images-script)

本文件给仓库级 agent 使用；子目录 `AGENTS.md` 只补充局部知识，不重复根规则。

## 概览

- 仓库分两条主线：Next.js 站点负责展示 runs / grid / 图片；Python 脚本负责生图、上传 R2、写入 Supabase。
- 当前网站数据链路以 Supabase + R2 为准；不要假设 Web 侧仍有本地文件降级读取。
- 术语约定：当前已接入、由上传脚本生成的 `display_*` / `thumb_*` 变体统一称为“展示页缩略图”；run 级 `image.*` 统一称为“封面图”，同级 `images/*` 统一称为“主页缩略图”。三者不是同一套资源，讨论与实现时必须明确区分。
- 现状约定：脚本侧已经识别并上传封面图/主页缩略图资产；网页首页当前通过 `/api/comfyui/runs` 消费 `assets.cover` / `assets.homepage_cards`，run 详情页通过 view bootstrap JSON 消费展示页缩略图。
- Next 16 / React 19 约定：本仓库的动态页面与 route handler 普遍使用 `params: Promise<...>` 形态；客户端页面侧常见 `use(params)`，服务端 route 侧常见 `await context.params`。
- 认证链路走 Supabase SSR：浏览器端 `lib/supabase-browser.ts`，服务端 `lib/supabase-auth.ts`，会话刷新在 `middleware.ts`。
- Web 部署目标是 OpenNext + Cloudflare：本地 `next dev` 会启 Miniflare，部分服务端能力通过 Workers bindings 读取。
- 当前分层知识文件已经覆盖主要强边界目录；像 `app/api/comfyui/run/[runDir]/` 这类 leaf route 继续继承父级规则，不再单开 `AGENTS.md`。

## 结构

```text
./
├── app/                    # App Router 页面与 API route
│   ├── api/comfyui/        # runs/access/workflow + 公开/私有对象代理
│   ├── auth/               # Supabase PKCE callback
│   ├── models/[runDir]/    # 模型详情页（虚拟网格 + workflow 下载）
│   ├── info/               # 关于页面（静态 Markdown）
│   └── privacy-policy/     # 隐私政策页面（静态 Markdown）
├── components/             # 业务组件 + UI primitives + auth provider
│   ├── comfyui/            # 虚拟网格/图片预览/blurhash
│   ├── home/               # 首页模型卡片/封面图/预览弹窗
│   └── ui/                 # shadcn/radix primitives
├── lib/                    # Supabase/R2/路径安全/共享类型
│   └── env/                # 环境变量集中读取
├── scripts/                # Python 生图、上传、CLI、辅助转换
│   ├── generation/         # 核心 runner + ComfyUI 客户端
│   ├── r2_upload/          # R2 上传 + Supabase 写入
│   ├── cli/                # 交互菜单与入口注册
│   └── other/              # CSV/YAML 资产转换工具
├── tests/                  # pytest（合约与可观测输出）
├── e2e/                    # Playwright 端到端
├── supabase/               # 本地配置与迁移
├── data/                   # 只读输入资产
│   ├── models/             # 模型配置（config.yaml + api.json + workflow.json）
│   └── prompts/            # X/Y prompt 资产（YAML + CSV）
├── hooks/                  # 共享前端行为
├── loaders/                # 自定义 Webpack loader（见 loaders/AGENTS.md）
├── public/                 # 静态资源（favicon 等）
├── types/                  # Next 生成类型（只读）
├── middleware.ts           # Supabase session refresh
└── main.py                 # Python 顶层入口（委托到 scripts）
```

## 去哪儿看

| 任务                  | 位置                                                                             | 备注                                                                           |
| --------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Python 顶层入口       | `main.py`                                                                        | 菜单/主 runner 的统一入口                                                      |
| 生图主入口            | `scripts/generation/comfyui_part1_generate.py`                                   | dry-run / retry / 落盘合约                                                     |
| 生图配置加载          | `scripts/generation/runner_config.py`                                            | `--config` YAML schema + repo-relative 资产校验；也识别封面图/主页缩略图源资产 |
| 并发 runner           | `scripts/generation/runner_coordinator.py`                                       | ThreadPoolExecutor 双池                                                        |
| ComfyUI 通信          | `scripts/generation/comfyui_client.py`                                           | HTTP / WS / 错误码                                                             |
| R2 上传入口           | `scripts/r2_upload/upload_images_to_r2.py`                                       | 编码、上传、写 Supabase                                                        |
| 上传规划              | `scripts/r2_upload/upload_planner.py`                                            | 多变体规划 + 并发编码；也处理 run 级静态图片资产上传                           |
| 资产转换脚本          | `scripts/other/convert_*.py`                                                     | 文件名遗留 `json`，实际输出 YAML 资产                                          |
| run 配置示例          | `data/models/example/config.yaml`                                                | `image-run-config/v1` 示例                                                     |
| 网站首页              | `app/page.tsx`                                                                   | 读取 `/api/comfyui/runs`；消费 `assets.cover` / `assets.homepage_cards`        |
| 模型详情页           | `app/models/[runDir]/page.tsx`                                                   | 拉取 view bootstrap JSON + 虚拟网格 + workflow 下载                            |
| App API 总约定        | `app/api/AGENTS.md`                                                              | `app/api/**/route.ts` 共享约束                                                 |
| ComfyUI API           | `app/api/comfyui/**/route.ts`                                                    | runs 列表 / access 授权 / workflow 下载                                        |
| Auth 回调特例         | `app/auth/AGENTS.md`                                                             | PKCE callback 直接交换 session                                                 |
| 站点壳层 / 登录入口   | `app/layout.tsx`、`components/site-header.tsx`                                   | ThemeProvider + AuthProvider + 登录弹窗入口                                    |
| Cloudflare / OpenNext | `next.config.ts`、`open-next.config.ts`、`cloudflare-env.d.ts`、`wrangler.jsonc` | 本地 Miniflare + Workers bindings / vars                                       |
| 服务端 Supabase       | `lib/supabase-auth.ts`                                                           | `server-only` + cookie session                                                 |
| 浏览器端 Supabase     | `lib/supabase-browser.ts`                                                        | AuthProvider 使用                                                              |
| runDir 校验           | `lib/comfyui-types.ts`                                                           | API 侧 `isValidRunDir()` type guard                                            |
| 路径安全              | `lib/comfyui-path.ts`                                                            | 共享路径工具与相对路径逃逸防护                                                 |
| R2 URL 构建           | `lib/r2-url.ts`                                                                  | 公开/私有 URL 与变体白名单                                                     |
| 会话刷新              | `middleware.ts`                                                                  | Edge middleware，不能引 `lib/supabase-auth.ts`                                 |
| Webpack loader        | `loaders/markdown-source-loader.cjs`                                             | 构建时将 `.md` 内联为 JS 字符串；见 `loaders/AGENTS.md`                        |

## 代码图

| 符号                          | 类型     | 位置                                           | 角色                |
| ----------------------------- | -------- | ---------------------------------------------- | ------------------- |
| `main`                        | function | `main.py`                                      | Python CLI 总入口   |
| `run`                         | function | `scripts/generation/comfyui_part1_generate.py` | 生图主流程          |
| `run_retry`                   | function | `scripts/generation/comfyui_part1_generate.py` | retry / replay 入口 |
| `GET`                         | function | `app/api/comfyui/runs/route.ts`                | runs 列表 API          |
| `GET`                         | function | `app/api/comfyui/run/[runDir]/access/route.ts` | 媒体授权 API           |
| `GET`                         | function | `app/api/comfyui/run/[runDir]/workflow/route.ts` | workflow 下载 API    |
| `publicObjectUrl`             | function | `lib/r2-url.ts`                                | 公开变体 URL        |
| `privateObjectUrl`            | function | `lib/r2-url.ts`                                | 私有图签名 URL      |
| `isValidRunDir`               | function | `lib/comfyui-types.ts`                         | runDir 形态校验     |
| `assertSafeRelativeImagePath` | function | `lib/comfyui-path.ts`                          | 相对图片路径校验    |

## 约定（项目特有）

- 语言边界：Node/Next 不直接调用 Python；网站只消费 Supabase + R2，不读取 Python 内部实现。
- Python：I/O 统一 `pathlib.Path`；生图产物固定为 `run.json` + `metadata.jsonl` + `images/`；写盘后保持 flush/fsync 语义。
- Python 运行资产：`scripts/generation/runner_config.py` 会把 run 目录下的 `image.*` 识别为封面图、`images/*` 识别为主页缩略图源资产；上传链路会继续把这些 run 级资产写入 R2 + Supabase。
- API：`app/api/**/route.ts` 保持 `runtime = "nodejs"`；错误响应返回固定短文案，不透出绝对路径、stack、凭证。
- Supabase：ComfyUI API 统一用 `createSupabaseAuthClient()`；浏览器端认证统一用 `createSupabaseBrowserClient()`；`app/auth/callback/route.ts` 为 PKCE 交换 session 的例外。
- Middleware 例外：`middleware.ts` 不能 import `lib/supabase-auth.ts`，因为后者依赖 `server-only` + `next/headers`。
- Cloudflare：本地 `next dev` 通过 `initOpenNextCloudflareForDev()` 提供 Miniflare 绑定；服务端访问 R2 bucket 走 `getCloudflareContext()`。
- 路径与 URL：API 入口的 `runDir` 先用 `lib/comfyui-types.ts:isValidRunDir()` 判形态；共享路径处理再走 `lib/comfyui-path.ts`；R2 URL 统一走 `lib/r2-url.ts`。
- 前端：大网格必须虚拟化；图片优先消费 R2 display/thumb 变体并配合 blurhash 占位，这套变体统一称为“展示页缩略图”。
- 前端首页：`/api/comfyui/runs` 当前会输出封面图/主页缩略图字段；不要把 run 详情页的展示页缩略图直接挪作首页卡片素材。
- 工具链：Python 用 `uv` + `pytest`（>=3.13）；Web 用 `pnpm` + Next 16 + React 19；E2E 用 Playwright。
- Supabase CLI：本仓库默认直接使用系统安装的 `supabase ...` 命令；既然已通过 `.deb` 安装 CLI，就不要再混用 `pnpm dlx supabase ...` 或 `npx supabase ...`。
- CI 现状：当前仓库没有 `.github/workflows/`；变更后的验证依赖本地 `uv` / `pnpm` / `supabase` 命令串联完成。
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
uv run python main.py --config data/models/example/config.yaml
uv run python main.py --config data/models/example/config.yaml --dry-run
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
supabase start
supabase db reset
supabase migration new <name>
```

## 分层文档

- `app/AGENTS.md`、`app/api/AGENTS.md`、`app/api/comfyui/AGENTS.md`、`app/auth/AGENTS.md`、`app/info/AGENTS.md`、`app/privacy-policy/AGENTS.md`、`app/models/[runDir]/AGENTS.md`：页面/API/Auth 的分层规则与 PKCE 特例。
- `components/AGENTS.md`、`components/ui/AGENTS.md`、`components/comfyui/AGENTS.md`、`components/home/AGENTS.md`：业务组件、UI primitives、虚拟网格/图片渲染约定。
- `lib/AGENTS.md`、`lib/env/AGENTS.md`：Supabase/R2/路径安全/共享类型边界与环境变量读取。
- `scripts/AGENTS.md`、`scripts/generation/AGENTS.md`、`scripts/r2_upload/AGENTS.md`、`scripts/cli/AGENTS.md`、`scripts/other/AGENTS.md`：Python 主代码域与子系统边界。
- `tests/AGENTS.md`、`e2e/AGENTS.md`、`supabase/AGENTS.md`、`data/AGENTS.md`、`hooks/AGENTS.md`、`types/AGENTS.md`：测试、迁移、资产、hooks、生成类型的局部规则。
