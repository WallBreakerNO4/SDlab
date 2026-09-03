<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-08-23 -->

# lib/ - Node 侧共享边界(Supabase + R2 + 路径安全 + 类型)

## 概览

- `lib/` 是 Web 侧共享边界层:认证态 Supabase 客户端、R2 URL 构建、路径安全、共享类型和 `cn()` 工具都在这里。

## 去哪儿看

| 场景                       | 位置                  | 备注                                             |
| -------------------------- | --------------------- | ------------------------------------------------ |
| 服务端 Supabase 客户端     | `supabase-auth.ts`    | `server-only` + cookie session + publishable key |
| 浏览器端 Supabase 客户端   | `supabase-browser.ts` | `AuthProvider` 使用                              |
| Supabase 相关类型          | `supabase-types.ts`   | run/image/variant 与 JSON 类型                   |
| R2 URL 构建                | `r2-url.ts`           | `publicObjectUrl()` / `privateObjectProxyUrl()`  |
| runDir 共享工具 / 路径校验 | `comfyui-path.ts`     | allowlist、相对路径、防逃逸                      |
| Web 领域类型               | `comfyui-types.ts`    | `RunSummary` / `RunDir` / type guard             |
| className 合并             | `utils.ts`            | `cn()`                                           |
| SEO metadata 构建          | `metadata-utils.ts`   | `buildSeoMetadata()`:统一生成 OG/Twitter Card/canonical/hreflang |
| 模型 SEO 元数据查询        | `model-metadata.ts`   | `getModelMetadata()`:从 Supabase 查 name/description/cover,1h cache |
| 模型指南数据层        | `model-guides.ts`       | `ModelGuide` / `ModelGuideIndex` 类型;frontmatter 契约校验;`buildGuideIndex()` / `getModelGuide()` / `resolveGuideLocale()`;消费 `lib/generated/model-guides.ts` 构建产物 |
| 模型指南 sitemap      | `model-guides-sitemap.ts` | `buildGuideSitemapEntries()`:仅为实际存在的指南语言生成 sitemap 条目与 hreflang;被 `app/sitemap.ts` 消费 |
| 构建期生成模块        | `generated/`（子目录）    | `model-guides.ts`:`pnpm guides:build` 由 `loaders/model-guide-data-builder.ts` 生成,提交到仓库;含元数据与正文,服务端使用,不要在客户端直接 import |
| 站点根 URL 常量            | `site-origin.ts`      | `SITE_ORIGIN`:`https://sdlab.wall-breaker-no4.xyz` |
| 首页 run 列表查询          | `run-list.ts`         | `listRunSummaries()`:`unstable_cache` 5min + tag `run-list`,查 `run_list_items` 视图并拼装 `assets.cover` / `assets.homepage_cards` |
| 浏览者偏好鉴权与写入       | `server-user-preferences.ts` | `server-only`;`requireViewerForPreferenceWrite()` + `setViewerShowNsfwPreference()` |
| NSFW cookie 工具           | `viewer-nsfw-cookie.ts` | `VIEWER_SHOW_NSFW_COOKIE` / `DEFAULT_SHOW_NSFW` / `setViewerShowNsfwCookie()` |
| Prompt 法典共享类型        | `prompt-types.ts`     | `TagNode` / `ChoiceNode` / `Prompt` / `Entry` / `TocNode` / `TargetModel` / `WeightMode` / `FileIndex` / `FileData` |
| Prompt 格式化引擎          | `prompt-formatter.ts` | `formatPrompt()`:结构化 Prompt → novelai / comfyui 文本;anima 权重模式对 comfyui 权重取平方;`hasPlaceholders()` / `countPlaceholders()` |
| Prompt 过滤                | `prompt-filter.ts`    | `filterEntriesExact` / `filterEntriesFuzzy`(Fuse.js)/ `filterToc` / `getAllTocKeys` |
| Prompt 数据加载            | `prompt-data-loader.ts` | `loadIndex()` / `loadFileData()`:从 `/data/prompts/*.json` fetch 并缓存 |
| Prompt 模型/权重 Context   | `prompt-model-context.tsx` | `ModelProvider` / `useModel()`,持久化到 localStorage |
| Prompt Choice Context     | `prompt-choice-context.tsx` | `ChoiceProvider` / `useChoices()`,持有用户在 Choice 节点上的选择 |
| 私有图片本地缓存        | `private-image-cache.ts`  | `"use client"`;按 userId 分空间的 Cache API 缓存;`loadPrivateImageObjectUrl()` / `readCachedPrivateImageObjectUrl()`;`PrivateImageLoadError` |
| R2 响应元数据工具       | `r2-response.ts`          | `server-only`;从 R2 对象提取 contentType 等 HTTP metadata 的共享类型与工具 |
| run 网格列可见性        | `run-grid-visibility.ts`  | `VisibleRunGridXColumn` / `VisibleRunGridColumns`;解析可见 X 列与允许的原始索引 |
| run 媒体授权 token       | `run-media-grant.ts`      | `server-only` + `node:crypto`;`ViewerVariant` / `RunMediaGrantClaims`;HMAC 签发 + `timingSafeEqual` 校验,服务 `access` route |
| 主题常量与解析          | `theme.ts`                | `THEME_STORAGE_KEY` / `THEME_COOKIE_NAME` / `THEME_COOKIE_MAX_AGE`;明暗色 oklch 值;`parseThemePreference()` / `ThemePreference` |
| 画师串收藏数据层        | `style-favorites.ts`      | `StyleKey` / `StyleItem` / `StyleFavoriteEntry` 类型与 guard + `fetchStyleFavorites()` / `upsertStyleFavorite()` / `deleteStyleFavorite()` 薄函数 |
| 模型对比共享合约        | `style-comparison.ts`     | 目录/详情/slice 类型与 guard、keyset cursor、上限解析、cache URL 与客户端纯函数 |
| 已发布模型目录缓存      | `style-comparison-server.ts` | `server-only`；查询已发布 run + X columns，`unstable_cache` 5 分钟 |

## 约定(本目录特有)

- ComfyUI API route 统一使用 `createSupabaseAuthClient()`;它依赖 `server-only` 与 `next/headers`。
- 浏览器端认证统一使用 `createSupabaseBrowserClient()`;不要在客户端自己拼 Supabase SSR 初始化。
- `middleware.ts` 是例外:因为运行在 Edge,不能 import `lib/supabase-auth.ts`,只能内联建 client。
- `publicObjectUrl()` 和 `privateObjectProxyUrl()` 是 Web 侧统一的 R2 URL 构建入口；两者都先验证 `runs/` key，不要在 route/组件里手拼对象 URL。
- `privateObjectProxyUrl(r2Key, grant)` 构建 `/api/private-object?key=...&grant=...`；grant 由 run media access 链路签发和校验，客户端不持有 R2 凭证，也不生成私有对象签名 URL。
- API 侧 `runDir` 形态判断走 `comfyui-types.ts:isValidRunDir()`;`comfyui-path.ts` 更偏共享路径安全与 allowlist 工具。
- SEO metadata 统一走 `metadata-utils.ts:buildSeoMetadata()`;各页面 `generateMetadata` 调用本函数即可一致产出 OG / Twitter Card / canonical / hreflang 标签。
- 模型详情页的 `og:image` 走 `model-metadata.ts:getModelMetadata()`;该函数带 1h 缓存,仅查询轻量字段。
- `site-origin.ts` 是 `SITE_ORIGIN` 的唯一定义点;sitemap / robots / metadata 均引用它,不要在各个文件中硬编码域名。
- Prompt 法典相关 lib 文件只服务 `/[locale]/prompts` 页面:`prompt-types.ts` 是与 PromptCodex schema 对齐的共享类型;`prompt-formatter.ts` 是唯一的目标模型文本格式化入口;`prompt-data-loader.ts` 只 fetch `public/data/prompts/*.json`(不读源 YAML);`prompt-model-context.tsx` / `prompt-choice-context.tsx` 是两个客户端 Context,不要在服务端组件里使用。
- `run-list.ts` 用 `unstable_cache` 包裹首页 run 列表查询,缓存 5 分钟并以 `run-list` tag 标记;刷新 run 数据时通过 `revalidateTag("run-list")` 失效,不要在页面层自己加缓存。
- `server-user-preferences.ts` 是 `server-only`,仅供 `app/api/viewer/**` 等 route 使用;浏览器端读取 NSFW 偏好只走 cookie(`viewer-nsfw-cookie.ts`),不要在客户端 import 本文件。
- 收藏身份用 `style_key`（`{collection_id}:{item_index}`）,跨 run 匹配只比较 style_key,永不比较 prompt 字符串;`y_index` 一律 0-based,仅收藏页拼跳转 URL 时 `#{y_index + 1}`。
- 模型对比目录默认/最大分页数均为 40；`parseStyleComparisonSliceBody()` 只接受 1–40 个 style keys 和 1–12 个 run dirs，所有 placement `y_index` 保持 0-based。
- `getCachedPublishedRuns()` 缓存已发布模型目录 5 分钟，cache key/tag 为模型目录级，不按用户或收藏分页重复构建。
- `buildPrivateObjectCacheUrl()` 仅生成去 grant、保留 `key` 的共享 edge cache URL；它不能代替授权，`app/api/private-object` 必须先执行 `verifyRunMediaGrant()` 与 key allowlist 校验，再做 cache lookup。

## 反模式

- 不要在 route/组件中绕过本目录直接拼磁盘路径、R2 URL 或代理 URL。
- 不要把 `supabase-auth.ts` 导入客户端组件;它是 `server-only`。
- 不要放宽 `runDir` / `imagePath` 校验来"临时兼容"坏数据。
- 不要把包含路径、bucket、环境变量的信息原样透传给 API 响应。
- 不要在各页面中手写 OG/Twitter Card metadata 模板;统一使用 `buildSeoMetadata()`。
- 不要在代码中硬编码域名;始终引用 `SITE_ORIGIN` 常量。
- 不要在客户端组件 import `prompt-formatter.ts` 以外的格式化逻辑,也不要在服务端组件 import `prompt-model-context.tsx` / `prompt-choice-context.tsx`(它们是客户端 Context)。
