<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-30 | Updated: 2026-05-30 -->

# i18n/ — next-intl 国际化配置

## 概览

- I18N 配置层，基于 `next-intl` 实现：路由定义、请求配置（消息加载）、导航辅助导出。本目录不做业务翻译，只承载框架集成代码。

## Key Files

| 文件 | 描述 |
|------|------|
| `routing.ts` | `defineRouting({ locales: ["zh", "en"], defaultLocale: "zh", localePrefix: "always" })`，全站国际化路由配置 |
| `request.ts` | `getRequestConfig()` 实现：从 `requestLocale` 解析当前语言，回退到 `defaultLocale`，按需加载 `messages/{locale}.json` |
| `navigation.ts` | 基于 `routing` 调用 `createNavigation()` 导出 `Link`、`redirect`、`usePathname`、`useRouter`、`getPathname`；组件中优先使用这些国际化感知的导航 API |

## For AI Agents

### Working In This Directory
- 路由配置变更（如新增语言）需同步更新 `messages/` 下的 JSON 文件、`middleware.ts` 的 matcher、以及所有 `hasLocale()` 校验点
- `localePrefix: "always"` 意味着所有路径都会带上 `/zh` 或 `/en` 前缀；API/静态资源由 middleware matcher 排除
- 导航 API 导出（`Link`、`useRouter` 等）必须从 `@/i18n/navigation` 导入，不要用 Next.js 原生的 `next/navigation`

### Common Patterns
- 组件中访问翻译：`const t = useTranslations("namespace")`
- 服务端访问翻译：`const t = await getTranslations({ locale, namespace })`
- 链接跳转：使用 `<Link href="/models/xxx">` 替代 Next.js 的 `<Link href="/zh/models/xxx">`，`Link` 会自动补 locale 前缀
- 语言校验：页面入口统一 `if (!hasLocale(routing.locales, locale)) notFound()`

## Dependencies

### Internal
- `messages/` - 翻译消息 JSON 文件
- `middleware.ts` - I18N 中间件（`createMiddleware(routing)`）
- `next.config.ts` - `createNextIntlPlugin("./i18n/request.ts")`

### External
- `next-intl` - 国际化框架（middleware / navigation / request / translations）
