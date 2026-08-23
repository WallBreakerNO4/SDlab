<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-08-23 -->

# components/ — 前端组件（业务 + 基础 UI）

## 概览

- `components/` 放组合/业务组件：既包含 ComfyUI viewer，也包含站点壳层、主题切换和浏览器端认证入口；基础组件集中在 `components/ui/`（shadcn/radix，约定见 `components/ui/AGENTS.md`）。

## 去哪儿看

| 场景                  | 位置                                     | 备注                                               |
| --------------------- | ---------------------------------------- | -------------------------------------------------- |
| 虚拟网格 + 预览       | `components/comfyui/virtual-grid.tsx`    | 虚拟滚动 + R2 图片源 + sticky 表头 + 弹窗预览      |
| Blurhash 占位渲染     | `components/comfyui/blurhash-canvas.tsx` | canvas 渲染 blurhash 编码                          |
| 网格图片组件          | `components/comfyui/grid-image.tsx`      | R2 图片 + blurhash 占位 + 加载状态                 |
| ComfyUI 领域组件约定  | `components/comfyui/AGENTS.md`           | 性能/交互/图片路径约定                             |
| 首页模型卡片          | `components/home/model-card.tsx`         | 封面图 + 描述展开 + 主页缩略图水平卷轴             |
| 首页预览弹窗          | `components/home/preview-dialog.tsx`     | 全屏大图预览弹窗                                   |
| 首页组件约定          | `components/home/AGENTS.md`              | 封面图/主页缩略图消费约定                          |
| 站点头部              | `components/site-header.tsx`             | 品牌、ThemeToggle、登录弹窗入口、收藏页入口（登录后）、用户菜单；`useTranslations("header")` 驱动多语言 |
| 站点页脚              | `components/site-footer.tsx`              | 版权、关于/隐私政策链接；`useTranslations("footer")` + `@/i18n/navigation` Link |
| 浏览器端认证 Provider | `components/auth-provider.tsx`           | `createSupabaseBrowserClient()` + session 监听     |
| 登录弹窗              | `components/auth-login-dialog.tsx`       | GitHub / Google / Microsoft OAuth 入口             |
| 主题切换              | `components/theme-toggle.tsx`            | `next-themes` + mounted guard，避免 hydration 闪烁 |
| Sidebar primitive     | `components/ui/sidebar.tsx`              | cookie 持久化 + 快捷键 + mobile Sheet fallback     |
| UI 组件使用示例       | `components/component-example.tsx`       | 用于展示/验证 UI primitives                        |
| JSON-LD 结构化数据    | `components/json-ld.tsx`                | `JsonLdWebsite` + `JsonLdBreadcrumbList`，客户端注入 schema.org 标签 |
| shadcn 配置           | `components.json`                        | aliases、style、cssVariables 等                    |
| Prompt 法典浏览器 UI  | `components/prompt/`                      | TOC + 虚拟滚动条目 + Tag/Choice/多角色渲染（见 `components/prompt/AGENTS.md`） |
| 收藏模型对比工作区   | `components/favorites/favorites-page.tsx` | 登录门控 + 收藏分页 + 已发布模型显隐 + 对比矩阵/预览 |
| 单收藏对比详情       | `components/favorites/favorite-comparison-detail.tsx` | 单一 `style_key` 的跨模型/测试场景详情 |
| 收藏组件约定         | `components/favorites/AGENTS.md`          | 对比目录、slice、row cache 与私有媒体约定 |
| 悬浮登录按钮            | `auth-floating-button.tsx`               | `"use client"`;未登录时悬浮按钮 → `AuthLoginDialog`;已登录显示头像下拉菜单 |
| shadcn 示例布局          | `example.tsx`                            | `ExampleWrapper` 布局组件,用于组件展示页面 |
| 用户偏好 Provider        | `user-preferences-provider.tsx`          | `"use client"`;用户偏好 Context（NSFW 等）,基于 `useAuth()` |
| Web Vitals 上报          | `web-vitals.tsx`                         | `"use client"`;`useReportWebVitals` → `/api/telemetry/web-vitals` |

## 约定（本目录特有）

- 业务组件优先复用 `components/ui/*` primitives（Button/Dialog/Card/Table/Skeleton 等）
- 认证入口统一经 `AuthProvider` + `useAuth()`；客户端组件只消费浏览器端会话，不直接导入 `server-only` 的 Supabase 实现
- 图片源：公开对象使用 `publicObjectUrl()`；私有对象使用 `privateObjectProxyUrl(key, grant)` 访问代理 route，不在组件中生成签名 URL
- 性能：大网格依赖虚拟化（`@tanstack/react-virtual`），避免一次性渲染全部 cell
- Blurhash：图片加载前展示 blurhash 占位（`blurhash-canvas.tsx`），提升感知加载速度
- JSON-LD：结构化数据组件（`json-ld.tsx`）是客户端组件，通过 `dangerouslySetInnerHTML` 注入 `<script type="application/ld+json">` 标签
- 主题切换通过 `next-themes`；按钮类组件需处理 mounted 前后的 hydration 差异
- 多语言：客户端组件使用 `useTranslations("namespace")` 获取翻译文案；导航链接使用 `@/i18n/navigation` 的 `Link` 而非 `next/link`
- 收藏对比：目录分页与 slice 必须分别遵守 40 条、40 style keys / 12 run dirs 上限；placement 的 `y_index` 保持 0-based。
- 私有媒体：组件只携带服务端签发的 grant 调用 `privateObjectProxyUrl()`；共享 edge cache 的去 grant URL 由 API route 构建，组件不得绕过授权或自行构造 cache key。

## 反模式

- 不要把 `components/ui/` 当业务逻辑堆放点；业务逻辑应留在 `components/comfyui` 或页面层
- 不要在客户端组件里导入 `lib/supabase-auth.ts` 或自行 new 服务端 Supabase client
- 不要在组件里硬编码文件系统根路径（所有文件读取都在 `lib/` + API route）
- 不要在组件中直接拼接 R2 URL；使用 `lib/r2-url.ts` 构建
