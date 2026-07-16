<!-- Generated: 2026-04-06 | Updated: 2026-07-16 -->
<!-- Commit: Anima Artist Mixer | 分支: dev -->

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
- Prompt 法典浏览器（路由 `/[locale]/prompts`）是新增的面向用户功能：客户端从 `public/data/prompts/*.json` 加载结构化 Prompt，渲染 Tag/Choice/多角色卡片并按目标模型格式化复制；源资产在 `data/prompt-codex/*.yaml`，运行时不直接读源 YAML。
- ComfyUI 生图链路已支持 Anima Artist Mixer：`workflow.anima_artist_mixer` 会把 Y 轴 general 标签留在正向 prompt，artists 标签单独写入 `artist_chain`；hash、回放与 strict retry 都把两者视为同一份生图输入。
- Mixer metadata 会额外持久化 `y_common_prompt`；展示页 bootstrap 通过可选 `yPromptParts` 向前端提供 Artist/Common Prompt 拆分，首列分别复制，缺失部分不渲染。

## 结构

```text
./
├── app/                    # App Router 页面与 API route
│   ├── [locale]/           # 区域化页面入口（layout + 首页 + info + privacy-policy + models + prompts）
│   ├── api/comfyui/        # runs/access/workflow + 公开/私有对象代理
│   ├── api/viewer/         # 浏览者偏好（NSFW 开关）
│   ├── api/telemetry/      # web-vitals 上报端点
│   ├── auth/               # Supabase PKCE callback
│   └── models/[runDir]/    # 模型详情页共享组件（由 [locale]/models/[runDir] 消费）
├── components/             # 业务组件 + UI primitives + auth provider
│   ├── comfyui/            # 虚拟网格/图片预览/blurhash
│   ├── home/               # 首页模型卡片/封面图/预览弹窗
│   ├── prompt/             # Prompt 法典浏览器 UI（见 components/prompt/AGENTS.md）
│   └── ui/                 # shadcn/radix primitives
├── i18n/                   # next-intl 国际化配置（路由/请求/导航）
├── messages/               # 翻译消息 JSON（zh.json / en.json）
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
│   ├── prompts/            # X/Y prompt 资产（YAML + CSV）
│   └── prompt-codex/       # Prompt 法典源 YAML（所长 NovelAI 个人法典）
├── hooks/                  # 共享前端行为
├── loaders/                # 自定义 Webpack loader（见 loaders/AGENTS.md）
├── public/                 # 静态资源（favicon + data/prompts 法典 JSON 产物）
├── types/                  # Next 生成类型（只读）
├── middleware.ts           # I18N 路由 + Supabase session refresh
└── main.py                 # Python 顶层入口（委托到 scripts）
```

## 去哪儿看

| 任务                  | 位置                                                                             | 备注                                                                           |
| --------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Python 顶层入口       | `main.py`                                                                        | 菜单/主 runner 的统一入口                                                      |
| 生图主入口            | `scripts/generation/comfyui_part1_generate.py`                                   | dry-run / retry / 落盘合约                                                     |
| 生图配置加载          | `scripts/generation/runner_config.py`                                            | `--config` YAML schema + repo-relative 资产校验；也识别封面图/主页缩略图源资产 |
| Prompt 网格/画师链      | `scripts/generation/prompt_grid.py`                                              | Y 轴 general/artists 拆分、权重 profile、prompt + artist chain hash                  |
| Workflow 参数注入         | `scripts/generation/workflow_patch.py`                                           | 标准 CLIPTextEncode 与 AnimaArtistPack 两种注入拓扑                             |
| 并发 runner           | `scripts/generation/runner_coordinator.py`                                       | ThreadPoolExecutor 双池                                                        |
| ComfyUI 通信          | `scripts/generation/comfyui_client.py`                                           | HTTP / WS / 错误码                                                             |
| R2 上传入口           | `scripts/r2_upload/upload_images_to_r2.py`                                       | 编码、上传、写 Supabase                                                        |
| 上传规划              | `scripts/r2_upload/upload_planner.py`                                            | 多变体规划 + 并发编码；也处理 run 级静态图片资产上传                           |
| 资产转换脚本          | `scripts/other/convert_*.py`                                                     | 文件名遗留 `json`，实际输出 YAML 资产                                          |
| run 配置示例          | `data/models/example/config.yaml`                                                | `image-run-config/v1` 示例                                                     |
| 网站首页              | `app/[locale]/page.tsx`                                                          | 读取 `/api/comfyui/runs`；消费 `assets.cover` / `assets.homepage_cards`        |
| 模型详情页           | `app/[locale]/models/[runDir]/page.tsx`                                          | 拉取 view bootstrap JSON + 虚拟网格 + workflow 下载                            |
| App API 总约定        | `app/api/AGENTS.md`                                                              | `app/api/**/route.ts` 共享约束                                                 |
| ComfyUI API           | `app/api/comfyui/**/route.ts`                                                    | runs 列表 / access 授权 / workflow 下载                                        |
| Auth 回调特例         | `app/auth/AGENTS.md`                                                             | PKCE callback 直接交换 session                                                 |
| 站点壳层 / 登录入口   | `app/[locale]/layout.tsx`、`components/site-header.tsx`                          | ThemeProvider + AuthProvider + NextIntlClientProvider + 登录弹窗入口             |
| 国际化路由配置        | `i18n/routing.ts`                                                                | `defineRouting({ locales, defaultLocale, localePrefix })`                      |
| 翻译消息文件          | `messages/zh.json`、`messages/en.json`                                           | 各 namespace 的翻译 key-value                                                  |
| Cloudflare / OpenNext | `next.config.ts`、`open-next.config.ts`、`cloudflare-env.d.ts`、`wrangler.jsonc` | 本地 Miniflare + Workers bindings / vars                                       |
| 服务端 Supabase       | `lib/supabase-auth.ts`                                                           | `server-only` + cookie session                                                 |
| 浏览器端 Supabase     | `lib/supabase-browser.ts`                                                        | AuthProvider 使用                                                              |
| runDir 校验           | `lib/comfyui-types.ts`                                                           | API 侧 `isValidRunDir()` type guard                                            |
| 路径安全              | `lib/comfyui-path.ts`                                                            | 共享路径工具与相对路径逃逸防护                                                 |
| R2 URL 构建           | `lib/r2-url.ts`                                                                  | 公开/私有 URL 与变体白名单                                                     |
| 会话刷新 + I18N       | `middleware.ts`                                                                  | Edge middleware：next-intl 路由 + Supabase session refresh                     |
| Webpack loader        | `loaders/markdown-source-loader.cjs`                                             | 构建时将 `.md` 内联为 JS 字符串；见 `loaders/AGENTS.md`                        |
| SEO metadata 工具     | `lib/metadata-utils.ts`                                                          | `buildSeoMetadata()`：统一生成 OG/Twitter Card/canonical/hreflang 标签        |
| 模型 SEO 元数据       | `lib/model-metadata.ts`                                                          | 从 Supabase 查询模型 name/description/cover 用于 og:image，带 1h cache        |
| 站点根 URL            | `lib/site-origin.ts`                                                             | `SITE_ORIGIN` 常量，供 sitemap/robots/metadata 共享                           |
| JSON-LD 结构化数据    | `components/json-ld.tsx`                                                         | `JsonLdWebsite` + `JsonLdBreadcrumbList` 客户端组件                           |
| robots.txt            | `app/robots.ts`                                                                  | 爬虫规则 + sitemap 引用                                                       |
| sitemap.xml           | `app/sitemap.ts`                                                                 | 多语言 sitemap + hreflang alternates，动态包含模型详情页                      |
| 错误页                | `app/[locale]/error.tsx`                                                         | 客户端错误页 + i18n + 重试/回首页                                            |
| 404 页                | `app/[locale]/not-found.tsx`                                                     | 客户端 404 页 + i18n + 回首页链接                                            |
| Prompt 法典浏览器     | `app/[locale]/prompts/page.tsx` + `components/prompt/`                              | 登录门控 + ModelProvider/ChoiceProvider + 客户端加载 `public/data/prompts/*.json` |
| Prompt 法典浏览器组件 | `components/prompt/AGENTS.md`                                                       | TOC + 虚拟滚动条目 + Tag/Choice/多角色渲染 + 格式化复制                    |
| Prompt 法典数据产物   | `public/data/prompts/index.json`、`public/data/prompts/files/*.json`               | 构建期产物，由源 YAML `data/prompt-codex/*.yaml` 生成；运行时只消费 JSON    |
| 浏览者 NSFW 偏好 API  | `app/api/viewer/preferences/nsfw/route.ts`                                        | GET 读 cookie / PATCH 写 Supabase `user_preferences` + cookie            |
| Web Vitals 上报       | `app/api/telemetry/web-vitals/route.ts`                                           | 接收 `console.log` 记录，204 空响应，不落库                              |

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
| `privateObjectProxyUrl`       | function | `lib/r2-url.ts`                                | 使用媒体 grant 构建私有对象代理 URL |
| `isValidRunDir`               | function | `lib/comfyui-types.ts`                         | runDir 形态校验     |
| `assertSafeRelativeImagePath` | function | `lib/comfyui-path.ts`                          | 相对图片路径校验    |
| `buildSeoMetadata`           | function | `lib/metadata-utils.ts`                       | SEO metadata 构建   |
| `getModelMetadata`           | function | `lib/model-metadata.ts`                       | 模型 SEO metadata   |
| `JsonLdWebsite`              | component | `components/json-ld.tsx`                     | WebSite schema     |
| `JsonLdBreadcrumbList`       | component | `components/json-ld.tsx`                     | BreadcrumbList schema |
| `SITE_ORIGIN`                | const    | `lib/site-origin.ts`                          | 站点根 URL          |
| `formatPrompt`              | function | `lib/prompt-formatter.ts`                    | 结构化 Prompt → 目标模型文本（novelai / comfyui + anima 权重模式） |
| `listRunSummaries`          | function | `lib/run-list.ts`                            | 首页 run 列表查询，`unstable_cache` 5min + tag `run-list` |
| `requireViewerForPreferenceWrite` | function | `lib/server-user-preferences.ts`       | 浏览者偏好写入的前置鉴权 |
| `PromptBrowserPage`         | component | `components/prompt/prompt-browser-page.tsx`   | 法典浏览器页面骨架 |
| `patch_workflow`            | function | `scripts/generation/workflow_patch.py`        | 注入标准 prompt 或 Anima Artist Mixer 参数 |

## 约定（项目特有）

- 语言边界：Node/Next 不直接调用 Python；网站只消费 Supabase + R2，不读取 Python 内部实现。
- Python：I/O 统一 `pathlib.Path`；生图产物固定为 `run.json` + `metadata.jsonl` + `images/`；写盘后保持 flush/fsync 语义。
- Python 运行资产：`scripts/generation/runner_config.py` 会把 run 目录下的 `image.*` 识别为封面图、`images/*` 识别为主页缩略图源资产；上传链路会继续把这些 run 级资产写入 R2 + Supabase。
- Anima Artist Mixer：`workflow.anima_artist_mixer: true` 仅允许 `backend=comfyui` 且 `model.family=anima`；workflow 必须是 KSampler 的 model/positive 同时连到启用的 `AnimaArtistCrossAttn`，再由 `AnimaArtistPack` 接收 `base_prompt` 与 `artist_chain`。
- 重发已发布 run 使用上传 CLI 的 `-F/--force-publish`；普通模式遇到不同 `release_id` 会拒绝。强制发布仍复用内容寻址资源，并在 Supabase 写入完成后最后覆盖 `view/current.json`。
- API：`app/api/**/route.ts` 保持 `runtime = "nodejs"`；错误响应返回固定短文案，不透出绝对路径、stack、凭证。
- Supabase：ComfyUI API 统一用 `createSupabaseAuthClient()`；浏览器端认证统一用 `createSupabaseBrowserClient()`；`app/auth/callback/route.ts` 为 PKCE 交换 session 的例外。
- Middleware 例外：`middleware.ts` 不能 import `lib/supabase-auth.ts`，因为后者依赖 `server-only` + `next/headers`。
- Cloudflare：本地 `next dev` 通过 `initOpenNextCloudflareForDev()` 提供 Miniflare 绑定；服务端访问 R2 bucket 走 `getCloudflareContext()`。
- 路径与 URL：API 入口的 `runDir` 先用 `lib/comfyui-types.ts:isValidRunDir()` 判形态；共享路径处理再走 `lib/comfyui-path.ts`；R2 URL 统一走 `lib/r2-url.ts`。
- 前端：大网格必须虚拟化；图片优先消费 R2 display/thumb 变体并配合 blurhash 占位，这套变体统一称为“展示页缩略图”。
- 前端首页：`/api/comfyui/runs` 当前会输出封面图/主页缩略图字段；不要把 run 详情页的展示页缩略图直接挪作首页卡片素材。
- Prompt 法典浏览器：运行时只消费 `public/data/prompts/*.json` 构建产物；源 YAML `data/prompt-codex/*.yaml` 是只读输入资产，不要在 Web 侧直接读取。目标模型/权重模式/Choice 选择的状态边界分别在 `lib/prompt-model-context.tsx` 与 `lib/prompt-choice-context.tsx`，格式化文本统一走 `lib/prompt-formatter.ts:formatPrompt()`。
- SEO：所有页面 `generateMetadata` 统一使用 `lib/metadata-utils.ts:buildSeoMetadata()` 构建 OG/Twitter Card/canonical/hreflang 标签，不要手写重复模板。模型详情页的 `og:image` 通过 `lib/model-metadata.ts:getModelMetadata()` 从 Supabase 查询封面图 URL。JSON-LD 结构化数据使用 `components/json-ld.tsx` 的客户端组件注入，不消耗 Worker CPU。
- 工具链：Python 用 `uv` + `pytest`（>=3.13）；Web 用 `pnpm` + Next 16 + React 19；E2E 用 Playwright。
- Supabase CLI：本仓库统一使用 `pnpm dlx supabase ...` 运行 Supabase 命令。
- CI 现状：当前仓库没有 `.github/workflows/`；变更后的验证依赖本地 `uv` / `pnpm` 命令串联完成。
- 协作文档与 git commit message 默认使用中文；涉及环境变量示例时优先更新 `.env.example`，不要直接读取/修改真实 `.env`。

## 分支与合并策略

- 分支模型：`dev` 为日常开发分支，`main` 为稳定发布分支。所有功能与修复先合入 `dev`，再由 `dev` 合并到 `main`。
- **合并时机由用户决定**：agent 不得在开发完成后自行触发 `dev` → `main` 合并。是否合并、何时合并、本次合并涵盖哪些内容，一律由用户明确指示后才能执行。
- `dev` → `main` 合并必须使用 `--no-ff` 选项，以保留一条明确的合并提交记录，便于追溯每一次发布窗口的内容与时间：
  ```bash
  git checkout main
  git merge --no-ff dev -m "merge: 合并 dev 到 main（<本次发布主题简述>）"
  ```
- 合并完成后，必须把该 `--no-ff` 合并提交同步回 `dev` 分支，使 `dev` 与 `main` 在合并点之后保持一致，避免后续再次合并时产生重复或冲突：
  ```bash
  git checkout dev
  git merge --ff-only main
  # 若 main 上除合并提交外无其他直推提交，等价于：git merge --ff-only main
  ```
- 禁止对 `main` 直接推送非合并提交；`main` 上的所有内容都应来自 `dev` 的 `--no-ff` 合并。
- 禁止用 fast-forward 合并 `dev` 到 `main`，否则会丢失合并节点，无法回溯发布边界。
- 禁止 agent 未经用户指示自行执行 `dev` → `main` 合并或同步回 `dev` 的操作；上述流程仅作为用户发起合并时的执行规范。

### 当前 `dev` 分支开发进展

以下为 `dev` 分支近期承载的主要开发主线（截至 2026-07-16，`dev` 已包含尚未发布到 `main` 的生图链路变更）：

- **Anima Artist Mixer**：新增 `data/models/Anima-base-1.0-Artist-Mixer/` 可执行配置；生图 runner 支持 general/artists 双通道注入，并将 `artist_chain` 纳入 metadata、prompt hash、run 回放和 strict retry 校验。
- **虚拟网格稳定性**：工具栏展开/收起时立即提交目标 viewport 宽度；私有图片 object URL 在 cell 重挂载间复用，由 `VirtualGrid` 卸载时统一释放。
- **Prompt 法典浏览器**：新增 `/[locale]/prompts` 浏览功能，含登录门禁、搜索匹配导航（从当前浏览位置跳转）、权重模式支持（Anima 模式，对所有标签统一平方处理）、ComfyUI 多角色提示词格式化（换行 + `Character N:` 前缀分隔角色）、Prompt 条目列表滚动对齐修复。
- **SEO 优化**：多语言 sitemap + hreflang alternates、隐私政策页上线、`buildSeoMetadata()` 统一 OG/Twitter Card/canonical、模型详情页 `og:image` 从 Supabase 查询封面图、JSON-LD 结构化数据（WebSite / BreadcrumbList）、构建元数据缺失标题与描述修复。
- **性能优化**：优化 Worker CPU 与边缘缓存复用以消除 503、优化缓存策略以减少 SSR 负载与响应延迟。
- **i18n hotfix**：将 I18N 中间件路由匹配从黑名单改为白名单机制。
- **基础设施维护**：依赖版本多次升级、`wrangler.jsonc` 配置修正、Supabase 远端 migration 同步并移除空 `seed.sql`、E2E 测试产物目录迁移到 `test-results/`、skills 更新、分层 `AGENTS.md` 文档校验与补全。

## 反模式

- 不改/不提交：真实环境文件（如 `.env` / `.env.local` / 其他私密配置）、`.venv/`、`node_modules/`、`.next/`、`.open-next/`、`outputs/`、遗留的 `comfyui_api_outputs/`。
- 不要把运行输出写进 `data/`；`data/` 只放可复现输入资产。
- 不要手改 `types/routes.d.ts`、`types/validator.ts` 等 Next 生成文件。
- 不要在页面/组件/route 中绕过 `lib/comfyui-path.ts` 或 `lib/r2-url.ts` 直接拼路径。
- 不要把 ComfyUI 整段响应、R2 key 细节、Supabase 凭证写进错误消息或日志。
- 修 bug 不要顺手大重构；测试失败不要删测或放宽断言来过。
- 未经用户明确要求，不修改 `package.json` / `pyproject.toml` 增加依赖。
- 不要把 `outputs/`、遗留的 `comfyui_api_outputs/`、`.next/`、`.open-next/`、`dist/`、`build/`、`.pytest_cache/`、`.ruff_cache/`、`.wrangler/`、`supabase/.temp/` 之类生成/缓存目录当源码或层级打分依据。

## 常用命令

```bash
# Python
uv sync
uv sync --no-dev
uv run python main.py --help
uv run python main.py --config data/models/example/config.yaml
uv run python main.py --config data/models/example/config.yaml --dry-run
uv run python main.py --config data/models/Anima-base-1.0-Artist-Mixer/config.yaml --dry-run
uv run pytest -q
uv run pytest -q tests/test_prompt_grid.py

# R2 上传
uv run python -m scripts.r2_upload.upload_images_to_r2 --help
uv run python -m scripts.r2_upload.upload_images_to_r2 --dry-run --run-dir outputs/run-xxx

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

- `app/AGENTS.md`、`app/api/AGENTS.md`、`app/api/comfyui/AGENTS.md`、`app/auth/AGENTS.md`、`app/[locale]/AGENTS.md`、`app/models/[runDir]/AGENTS.md`：页面/API/Auth/I18N 的分层规则与 PKCE 特例。
- `components/AGENTS.md`、`components/ui/AGENTS.md`、`components/comfyui/AGENTS.md`、`components/home/AGENTS.md`、`components/prompt/AGENTS.md`：业务组件、UI primitives、虚拟网格/图片渲染约定、Prompt 法典浏览器 UI。
- `i18n/AGENTS.md`、`messages/AGENTS.md`：国际化路由配置与翻译消息约定。
- `lib/AGENTS.md`、`lib/env/AGENTS.md`：Supabase/R2/路径安全/共享类型边界与环境变量读取。
- `scripts/AGENTS.md`、`scripts/generation/AGENTS.md`、`scripts/r2_upload/AGENTS.md`、`scripts/cli/AGENTS.md`、`scripts/other/AGENTS.md`：Python 主代码域与子系统边界。
- `tests/AGENTS.md`、`e2e/AGENTS.md`、`supabase/AGENTS.md`、`data/AGENTS.md`、`hooks/AGENTS.md`、`types/AGENTS.md`、`public/AGENTS.md`：测试、迁移、资产、hooks、生成类型、静态资源的局部规则。
