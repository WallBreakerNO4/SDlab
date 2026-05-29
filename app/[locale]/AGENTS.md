<!-- Parent: ../../AGENTS.md -->
<!-- Generated: 2026-05-30 | Updated: 2026-05-30 -->

# app/[locale]/ — 区域化页面层

## 概览

- I18N 改造后，所有面向用户的页面都迁入 `[locale]` 动态路由段。`app/layout.tsx` 现在是透传壳，真正的 HTML/Layout/Providers 装配在 `app/[locale]/layout.tsx` 中完成。

## Key Files

| 文件 | 描述 |
|------|------|
| `layout.tsx` | 全站根 Layout：字体系列、ThemeProvider、NextIntlClientProvider、AuthProvider、UserPreferencesProvider、SiteHeader、SiteFooter、Toaster、WebVitals |
| `page.tsx` | 首页（Server Component）：验证 locale → `setRequestLocale()` → `listRunSummaries()` → 渲染 `HomePageClient` |
| `info/page.tsx` | 关于页面：`force-static` + `react-markdown`，根据 locale 选择 `info-page.md` 或 `info-page.en.md` |
| `privacy-policy/page.tsx` | 隐私政策页：`force-static` + `react-markdown`，根据 locale 选择 `privacy-policy-page.md` 或 `privacy-policy-page.en.md` |
| `models/[runDir]/page.tsx` | 模型详情页（Server Component）：验证 locale + `isValidRunDir()` → 渲染 `ModelDetailClientPage(runDir)` |

## For AI Agents

### Working In This Directory
- **Locale 校验是强制步骤**：每个 `page.tsx` / `layout.tsx` 入口必须先 `if (!hasLocale(routing.locales, locale)) notFound()`
- 校验通过后必须调用 `setRequestLocale(locale)`，否则 `next-intl` 服务端 API（如 `getTranslations`）会报错
- `params` 统一使用 `Promise<{ locale: string }>` 形态；`await params` 后解构 locale
- `app/[locale]/layout.tsx` 替代了旧 `app/layout.tsx` 的大部分职责；不要在旧的 `app/layout.tsx` 里加 Provider 或字体
- 根 `/` 的 redirect（`app/page.tsx` → `/zh`）保持不变；新增语言时需要同步更新默认跳转目标
- 页面元数据（`generateMetadata`）使用 `getTranslations({ locale, namespace: "metadata.xxx" })` 获取翻译后的 title/description

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

## Dependencies

### Internal
- `app/models/[runDir]/` - 模型详情页的客户端组件（`ModelDetailClientPage`）
- `app/home-page-client.tsx` - 首页客户端组件
- `components/` - 全站组件（header、footer、auth provider 等）
- `i18n/routing.ts` - locale 白名单
- `i18n/navigation.ts` - 国际化 Link/useRouter
- `messages/` - 翻译 JSON
- `data/` - Markdown 静态页面源文件（含 `.en.md` 变体）
- `lib/run-list.ts` - 首页模型列表查询

### External
- `next-intl` - `useTranslations` / `getTranslations` / `setRequestLocale` / `hasLocale` / `NextIntlClientProvider`
- `react-markdown` - 静态页面渲染
