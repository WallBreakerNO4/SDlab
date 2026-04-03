# app/ — Next.js 展示网站（App Router）

## 概览

- 页面层负责 runs / run detail / auth callback 展示与全站 layout 装配；数据从 Supabase API 读取，图片从 R2 公开 URL 或私有签名 URL 读取。
- 术语约定：run 详情页网格里消费的 `display_*` / `thumb_*` 变体叫“展示页缩略图”；run 级 `image.*` 属于封面图，同级 `images/*` 属于主页缩略图集合。当前网页首页已经通过 `/api/comfyui/runs` 消费封面图与主页缩略图字段。

## 去哪儿看

| 场景                | 位置                                             | 备注                                                          |
| ------------------- | ------------------------------------------------ | ------------------------------------------------------------- |
| 首页 runs 列表      | `app/page.tsx`                                   | 拉 `/api/comfyui/runs`；消费封面图与主页缩略图字段            |
| run 详情页          | `app/runs/[runDir]/page.tsx`                     | 并行拉 detail + grid，前端做 type guard，并显示 workflow 下载 |
| Auth 回调页         | `app/auth/callback/route.ts`                     | OAuth 回跳处理                                                |
| Auth 局部约定       | `app/auth/AGENTS.md`                             | PKCE session 交换特例                                         |
| API 总约定          | `app/api/AGENTS.md`                              | `runtime` / 错误响应 / 鉴权边界                               |
| API：runs 列表      | `app/api/comfyui/runs/route.ts`                  | Supabase 查询                                                 |
| API：run 详情       | `app/api/comfyui/run/[runDir]/route.ts`          | 返回 `run`、`xLabels`、`yLabels`、`x_columns`、`y_indexes`    |
| API：grid 索引      | `app/api/comfyui/run/[runDir]/grid/route.ts`     | blurhash_cells + 网格索引                                     |
| API：row 级图片查询 | `app/api/comfyui/run/[runDir]/row/route.ts`      | 变体 URL + metadata                                           |
| API：workflow 下载  | `app/api/comfyui/run/[runDir]/workflow/route.ts` | 认证后读取 R2 workflow artifact 并返回下载响应                |
| 布局与样式入口      | `app/layout.tsx`、`app/globals.css`              | token / fonts / ThemeProvider / AuthProvider                  |
| 站点头部与登录入口  | `components/site-header.tsx`                     | ThemeToggle + 登录弹窗 + 用户菜单                             |
| API 局部约定        | `app/api/comfyui/AGENTS.md`                      | 当前已落地的 route 细则                                       |

## 约定（本目录特有）

- App Router API 保持 `export const runtime = "nodejs"`。
- ComfyUI API 统一经 `createSupabaseAuthClient()`；`auth/callback` 为 PKCE 特例，直接用 `createServerClient()` 交换 session。
- `app/api/` 负责 route 级共性约束；当前已落地的细分子域是 `app/api/comfyui/`。
- Next 16 / React 19：本目录的动态页面与 route handler 普遍使用 `params: Promise<...>` 形态；客户端页面可 `use(params)`，route 中则 `await context.params`。
- run 详情页当前除了 summary + grid，还消费 `run.workflow.download_url` 暴露 workflow 下载入口；页面层只消费 URL，不直接接触 R2 bucket 细节。
- 脚本侧已经适配 run 级封面图与主页缩略图资产；网页首页当前通过 `/api/comfyui/runs` 返回的 `assets.cover` / `assets.homepage_cards` 消费这些字段。
- 首页当前使用独立的封面图/主页缩略图字段；不要把 run 详情页的展示页缩略图语义直接挪作首页卡片素材。
- `app/layout.tsx` 负责挂载 `ThemeProvider`、`AuthProvider`、`SiteHeader`、`SiteFooter`；全站认证/主题入口从这里接入。
- 页面 fetch 后先做 type guard，再进入渲染状态机；错误态与 not-found 分开处理。
- 图片路径/对象 key 不在页面层手拼；公开变体走 `publicObjectUrl()`，私有对象走 `privateObjectUrl()` 返回的短期签名 URL。
- 本目录当前不维护本地文件流降级 route；Web 侧以 Supabase + R2 为准。

## 反模式

- 不要在页面或 route 里绕过 `lib/r2-url.ts` / `lib/comfyui-path.ts` 手工拼路径。
- 不要在 API 响应里返回异常堆栈、本机路径或凭证相关细节。
- 不要把 `.next/` 或 `types/*.d.ts` 当可编辑源码。
- 不要在 ComfyUI API 里直接创建裸 `createServerClient()`；统一走 `lib/supabase-auth.ts`。
