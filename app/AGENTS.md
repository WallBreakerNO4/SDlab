<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-08-23 -->

# app/ — Next.js 展示网站（App Router）

## 概览

- 页面层负责首页模型目录 / 模型详情 / 收藏模型对比 / about / privacy / auth callback 展示与全站 layout 装配；数据从 Supabase API 与 R2 view JSON 读取，公开图片直连 R2，私有对象经 grant 代理读取。
- 所有面向用户的页面位于 `app/[locale]/` 动态路由段；`app/layout.tsx` 是纯透传壳；`app/models/[runDir]/` 是纯组件模块，由 `app/[locale]/models/[runDir]/page.tsx` 消费。
- 术语约定：run 详情页网格里消费的 `display_*` / `thumb_*` 变体叫“展示页缩略图”；run 级 `image.*` 属于封面图，同级 `images/*` 属于主页缩略图集合。网页首页通过 `/api/comfyui/runs` 消费封面图与主页缩略图字段。

## 去哪儿看

| 场景                | 位置                                             | 备注                                                          |
| ------------------- | ------------------------------------------------ | ------------------------------------------------------------- |
| 首页 runs 列表      | `app/[locale]/page.tsx`                          | 拉 `/api/comfyui/runs`；消费封面图与主页缩略图字段            |
| 首页客户端组件       | `app/home-page-client.tsx`                       | `useTranslations("home")` 驱动多语言 Hero/Models 区域          |
| 模型详情页（入口）   | `app/[locale]/models/[runDir]/page.tsx`          | locale 校验 + runDir 校验 → 委托 `ModelDetailClientPage`      |
| 模型详情页（组件）   | `app/models/[runDir]/model-detail-client.tsx`    | 拉取 view bootstrap JSON + 虚拟网格 + workflow 下载           |
| 收藏模型对比页       | `app/[locale]/favorites/page.tsx`                | 登录门控 + 收藏行 × 已发布模型列矩阵；noindex                 |
| 单收藏对比详情       | `app/[locale]/favorites/[styleKey]/page.tsx`     | 同一 `style_key` 的跨模型详情；委托 `FavoriteComparisonDetail` |
| 模型指南页           | `app/[locale]/guides/[modelKey]/page.tsx`        | 静态预渲染的 Markdown 指南；draft 草稿不发布；locale 缺失重定向 |
| Auth 回调页         | `app/auth/callback/route.ts`                     | OAuth 回跳处理                                                |
| Auth 局部约定       | `app/auth/AGENTS.md`                             | PKCE session 交换特例                                         |
| API 总约定          | `app/api/AGENTS.md`                              | `runtime` / 错误响应 / 鉴权边界                               |
| API：runs 列表      | `app/api/comfyui/runs/route.ts`                  | Supabase 查询                                                 |
| API：媒体授权       | `app/api/comfyui/run/[runDir]/access/route.ts`   | SFW/NSFW 视图 grant 分发                                      |
| API：workflow 下载  | `app/api/comfyui/run/[runDir]/workflow/route.ts` | 认证后读取 R2 workflow artifact 并返回下载响应                |
| 公开对象代理        | `app/api/public-object/route.ts`                 | R2 公开对象直接回源                                           |
| 私有对象代理        | `app/api/private-object/route.ts`                | R2 私有对象代理（需 grant）                                   |
| 关于页              | `app/[locale]/info/page.tsx`                     | `force-static` + locale 选择 .md 或 .en.md                    |
| 隐私政策页          | `app/[locale]/privacy-policy/page.tsx`           | `force-static` + locale 选择 .md 或 .en.md                    |
| 全站 Layout          | `app/[locale]/layout.tsx`                        | ThemeProvider + AuthProvider + NextIntlClientProvider + SiteHeader + SiteFooter |
| 根壳层（透传）       | `app/layout.tsx`                                 | 仅透传 `children`，实际 Layout 在 `[locale]/layout.tsx`       |
| robots.txt            | `app/robots.ts`                                  | 爬虫规则 + sitemap 引用；通过 `SITE_ORIGIN` 构建完整 URL      |
| sitemap.xml           | `app/sitemap.ts`                                 | 多语言 sitemap + hreflang alternates；动态注入模型详情页     |
| API 局部约定        | `app/api/comfyui/AGENTS.md`                      | route 细则                                       |
| Viewer API 局部约定 | `app/api/viewer/AGENTS.md`                       | NSFW 偏好、收藏 CRUD、模型对比目录/详情/slice                 |
| I18N 页面层约定      | `app/[locale]/AGENTS.md`                         | locale 校验 + 导航 + 翻译约定                                  |
| 模型详情页组件约定   | `app/models/[runDir]/AGENTS.md`                  | 数据流、type guard、hook 设计                                 |

## 约定（本目录特有）

- App Router API 保持 `export const runtime = "nodejs"`。
- ComfyUI API 统一经 `createSupabaseAuthClient()`；`auth/callback` 为 PKCE 特例，直接用 `createServerClient()` 交换 session。
- `app/api/` 负责 route 级共性约束；`app/api/comfyui/` 与 `app/api/viewer/` 分别承载 run 数据和登录浏览者状态。
- Next 16 / React 19：本目录的动态页面与 route handler 普遍使用 `params: Promise<...>` 形态；客户端页面可 `use(params)`，route 中则 `await context.params`。
- I18N：`app/layout.tsx` 是纯透传壳，不挂任何 Provider 或字体；全站 Layout 在 `app/[locale]/layout.tsx`。
- I18N：所有带 locale 的页面入口必须先 `hasLocale(routing.locales, locale)` + `setRequestLocale(locale)`。
- I18N：根 `/` 通过 `app/page.tsx` 重定向到 `/zh`。
- `app/[locale]/info/` / `app/[locale]/privacy-policy/`：`force-static` + `react-markdown`，根据 locale 选择 `.md` 或 `.en.md` Markdown 源文件。
- run 详情页使用 view bootstrap JSON（`view/current.json` → `view/v2/{release_id}/bootstrap.*.json`）获取 detail + grid 数据，不通过独立 API route。
- 脚本侧适配 run 级封面图与主页缩略图资产；网页首页通过 `/api/comfyui/runs` 返回的 `assets.cover` / `assets.homepage_cards` 消费这些字段。
- 首页使用独立的封面图/主页缩略图字段；不要把 run 详情页的展示页缩略图语义直接挪作首页卡片素材。
- SEO：`sitemap.ts` 为每个页面生成两个 locale 的条目并添加 hreflang alternates；模型指南页仅对实际存在语言的指南生成条目（经 `buildGuideSitemapEntries()`）。`robots.ts` 允许所有爬虫爬取页面但禁止 `/api/` 和 `/auth/`。二者均引用 `lib/site-origin.ts` 的 `SITE_ORIGIN`。
- 页面 fetch 后先做 type guard，再进入渲染状态机；错误态与 not-found 分开处理。
- 图片路径/对象 key 不在页面层手拼；公开变体走 `publicObjectUrl()`，私有对象走 `privateObjectProxyUrl(key, grant)` 构建的 `/api/private-object` URL。
- `/api/private-object` 必须先验证 media grant 与对象 key 范围，再访问边缘 cache；共享 cache URL 归一化为仅保留 `key` 参数，因此会去掉 `grant` 及其他 query 参数。
- 本目录不维护本地文件流降级 route；Web 侧以 Supabase + R2 为准。

## 反模式

- 不要在页面或 route 里绕过 `lib/r2-url.ts` / `lib/comfyui-path.ts` 手工拼路径。
- 不要在 API 响应里返回异常堆栈、本机路径或凭证相关细节。
- 不要把 `.next/` 或 `types/*.d.ts` 当可编辑源码。
- 不要在 ComfyUI API 里直接创建裸 `createServerClient()`；统一走 `lib/supabase-auth.ts`。
- 不要往 `app/layout.tsx` 里加 Provider（它是透传壳）；所有全局 Provider 放 `app/[locale]/layout.tsx`。
- 不要使用 `next/link` 或 `next/navigation` 的原生 API 做用户页面导航；统一使用 `@/i18n/navigation` 的 `Link` / `useRouter`。
- 不要在页面 `generateMetadata` 中手写 OG/Twitter Card 模板；统一使用 `lib/metadata-utils.ts:buildSeoMetadata()`。
