<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-30 | Updated: 2026-08-23 -->

# app/[locale]/ — 区域化页面层

## 概览

- 所有面向用户的页面位于 `[locale]` 动态路由段。`app/layout.tsx` 是透传壳，真正的 HTML/Layout/Providers 装配在 `app/[locale]/layout.tsx` 中完成。

## Key Files

| 文件 | 描述 |
|------|------|
| `layout.tsx` | 全站根 Layout：字体系列、ThemeProvider、NextIntlClientProvider、AuthProvider、UserPreferencesProvider、SiteHeader、SiteFooter、Toaster、WebVitals、JSON-LD |
| `page.tsx` | 首页（Server Component）：验证 locale → `setRequestLocale()` → `listRunSummaries()` → 渲染 `HomePageClient` |
| `error.tsx` | 客户端错误页：`"use client"` + `Empty` 组件 + i18n + 重试按钮 + 回首页链接 |
| `not-found.tsx` | 客户端 404 页：`"use client"` + `Empty` 组件 + i18n + 回首页链接 |
| `info/page.tsx` | 关于页面：`force-static` + `react-markdown`，根据 locale 选择 `info-page.md` 或 `info-page.en.md` |
| `privacy-policy/page.tsx` | 隐私政策页：`force-static` + `react-markdown`，根据 locale 选择 `privacy-policy-page.md` 或 `privacy-policy-page.en.md` |
| `models/[runDir]/page.tsx` | 模型详情页（Server Component）：验证 locale + `isValidRunDir()` → 渲染 `ModelDetailClientPage(runDir)` |
| `prompts/page.tsx` | Prompt 法典浏览器页（Server Component）：验证 locale → `buildSeoMetadata()` → 用 `ModelProvider` + `ChoiceProvider` 包裹 `PromptBrowserPage`；未登录时由客户端组件渲染登录门控 |
| `favorites/page.tsx` | 画师串收藏页（Server Component）：验证 locale → `buildSeoMetadata()` + `robots: { index: false }` → 渲染 `components/favorites/favorites-page.tsx`；未登录由客户端渲染登录引导 |
| `favorites/[styleKey]/page.tsx` | 单收藏模型对比页（Server Component）：验证 locale、解码 `styleKey` → `buildSeoMetadata()` + `robots: { index: false }` → 渲染 `FavoriteComparisonDetail` |
| `guides/[modelKey]/page.tsx` | 模型使用指南页（静态预渲染）：`dynamicParams = false` + `generateStaticParams()` 从 `lib/generated/model-guides.ts` 生成；frontmatter `draft: true` 不进索引；locale 缺失时 `redirect()` 到可用语言，无可用语言 `notFound()` |

## For AI Agents

### Working In This Directory
- **Locale 校验是强制步骤**：每个 `page.tsx` / `layout.tsx` 入口必须先 `if (!hasLocale(routing.locales, locale)) notFound()`
- 校验通过后必须调用 `setRequestLocale(locale)`，否则 `next-intl` 服务端 API（如 `getTranslations`）会报错
- `params` 统一使用 `Promise<...>` 形态；普通页面为 `{ locale: string }`，动态详情页再加入 `runDir` / `styleKey`，统一 `await params` 后解构
- 全站 Provider 与字体装配在 `app/[locale]/layout.tsx`；不要在 `app/layout.tsx` 里加 Provider 或字体
- 根 `/` 通过 `app/page.tsx` redirect 到 `/zh`；新增语言时需要同步更新默认跳转目标
- 页面元数据（`generateMetadata`）使用 `getTranslations(...)` 获取翻译后的 title/description；收藏页使用 `styleFavorites` namespace，并保持 `robots.index = false`
- error 和 not-found 页面都是客户端组件（`"use client"`），通过 `useTranslations("metadata.error")` / `useTranslations("metadata.notFound")` 获取翻译文案

### Common Patterns
- 服务端入口模板：
  ```tsx
  export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
    const { locale } = await params;
    if (!hasLocale(routing.locales, locale)) notFound();
    setRequestLocale(locale);
    // ... 数据获取 → 渲染
  }
  ```
- 导航链接使用 `@/i18n/navigation` 的 `Link`，不要用 `next/link` 原生 Link（后者不会自动补 locale 前缀）
- 静态页面（info / privacy-policy）设置 `export const dynamic = "force-static"`，构建时根据 `generateStaticParams()` 预渲染所有 locale 版本

### Testing Requirements
- E2E 测试需要覆盖两种 locale 下的页面访问
- 确保 `/zh/models/xxx` 和 `/en/models/xxx` 都能正常渲染
- 静态页面的 `<title>` 和 `<meta description>` 应随 locale 变化

## Subdirectories

| 目录 | 用途 |
|------|------|
| `info/` | 关于页面（静态 Markdown） |
| `privacy-policy/` | 隐私政策页面（静态 Markdown） |
| `models/[runDir]/` | 模型详情页（委托 `app/models/[runDir]/` 的组件） |
| `prompts/` | Prompt 法典浏览器（委托 `components/prompt/`，见 `components/prompt/AGENTS.md`） |
| `favorites/` | 画师串收藏矩阵与单收藏跨模型详情（委托 `components/favorites/`，见 `components/favorites/AGENTS.md`） |
| `guides/` | 模型使用指南页 `[modelKey]`（构建期索引 + Markdown 渲染） |

## Dependencies

### Internal
- `app/models/[runDir]/` - 模型详情页的客户端组件（`ModelDetailClientPage`）
- `app/home-page-client.tsx` - 首页客户端组件
- `components/` - 全站组件（header、footer、auth provider 等）
- `components/prompt/` - Prompt 法典浏览器 UI（`PromptBrowserPage` + 子组件）
- `components/favorites/` - 收藏矩阵、对比数据加载与单收藏详情 UI
- `lib/prompt-model-context.tsx` / `lib/prompt-choice-context.tsx` - 法典页面的两个 Context Provider
- `i18n/routing.ts` - locale 白名单
- `i18n/navigation.ts` - 国际化 Link/useRouter
- `messages/` - 翻译 JSON
- `data/` - Markdown 静态页面源文件（含 `.en.md` 变体）
- `lib/run-list.ts` - 首页模型列表查询
- `lib/model-guides.ts` / `lib/generated/model-guides.ts` - 指南索引与 frontmatter 契约校验

### External
- `next-intl` - `useTranslations` / `getTranslations` / `setRequestLocale` / `hasLocale` / `NextIntlClientProvider`
- `react-markdown` - 静态页面渲染
