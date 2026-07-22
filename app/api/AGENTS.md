<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-07-20 -->

# app/api/ — App Router API 共性约定

## 概览

- 本目录放 Web 侧服务端 route：ComfyUI run 查询、浏览者偏好/收藏/模型对比、R2 对象代理与 telemetry；子目录只补充各自 payload 细节。

## 去哪儿看

| 场景             | 位置                                   | 备注                                      |
| ---------------- | -------------------------------------- | ----------------------------------------- |
| API 共性入口     | `app/api/` 下各 `route.ts`             | 统一 Node runtime、短错误响应、服务端鉴权 |
| ComfyUI API 细则 | `app/api/comfyui/AGENTS.md`            | runs / detail / grid / row                |
| Viewer API 细则  | `app/api/viewer/AGENTS.md`             | NSFW 偏好、收藏 CRUD、模型对比目录/详情/slice |
| 浏览者 NSFW 偏好   | `app/api/viewer/preferences/nsfw/route.ts` | GET 读 cookie / PATCH 写 Supabase `user_preferences` + cookie |
| 画师串收藏 API     | `app/api/viewer/style-favorites/route.ts`、`app/api/viewer/style-favorites/[styleKey]/route.ts` | GET 列表 / PUT upsert / DELETE；未登录 401 |
| 模型对比目录/详情  | `app/api/viewer/style-comparison/route.ts`、`app/api/viewer/style-comparison/[styleKey]/route.ts` | keyset 分页（每页最多 40）+ 已发布模型目录 |
| 模型对比 slice     | `app/api/viewer/style-comparison/slice/route.ts` | 最多 40 个 style keys / 12 个 run dirs，返回 placement + media grants |
| Web Vitals 上报    | `app/api/telemetry/web-vitals/route.ts` | 接收并 `console.log` 记录，204 空响应，不落库 |
| 共享鉴权客户端   | `lib/supabase-auth.ts`                 | `createSupabaseAuthClient()`              |
| 浏览者偏好鉴权   | `lib/server-user-preferences.ts`       | `requireViewerForPreferenceWrite()` + `setViewerShowNsfwPreference()` |
| NSFW cookie 工具 | `lib/viewer-nsfw-cookie.ts`            | `VIEWER_SHOW_NSFW_COOKIE` / `setViewerShowNsfwCookie()` |
| 路径与 URL 边界  | `lib/comfyui-path.ts`、`lib/r2-url.ts` | 参数校验与 URL 生成入口                   |

## 约定（本目录特有）

- route 统一保持 `export const runtime = "nodejs"`；不要把本目录迁到 Edge runtime。
- 需要用户态的 route 统一走 `createSupabaseAuthClient()`；`app/auth/callback/route.ts` 不属于本目录里的共性约束。
- Next 16 / React 19：动态 route handler 常见 `context.params: Promise<...>` 形态；在 handler 内统一 `await context.params`，不要按旧版同步对象写法假设。
- 对外错误响应保持固定短文案；不要透出 SQL、路径、bucket、凭证、堆栈。
- `app/api/telemetry/web-vitals` 是纯日志端点：解析失败或空 body 时静默返回 204，不要抛 500，不要把上报内容写入数据库或响应体。
- `app/api/viewer/**` 涉及用户偏好写入：PATCH 必须经 `requireViewerForPreferenceWrite()` 鉴权后写 Supabase，并在响应里通过 `setViewerShowNsfwCookie()` 同步 cookie；GET 可在未登录时仅读 cookie 返回默认值。
- `app/api/viewer/style-favorites` 是登录态收藏 API：PUT 先校验 body（`style_key` 匹配 `^[^:]+:\d+$` 且 ≤200、`label` 非空 ≤1000）再鉴权 upsert；DELETE 路径参数 `styleKey` 含 `:`，客户端必须 `encodeURIComponent`；未登录一律 401。
- `app/api/viewer/style-comparison` 全部要求登录：目录分页上限 40，slice 请求上限为 40 个 `style_key` / 12 个 `run_dir`；placement 的 `y_index` 保持 0-based，模型目录通过 `unstable_cache` 缓存 5 分钟。
- `app/api/private-object` 必须在 edge cache lookup 前完成 grant 校验与对象 key allowlist 校验；cache URL 可以移除 `grant` 以跨用户复用，但必须保留 `key`，禁止把未授权请求送入共享 cache。
- 进入查询前先校验输入：`runDir` 先做 type guard；不要在 route 内自由拼接路径或对象 key。
- 子目录文档优先级高于本文件：`comfyui/` 讲 run payload 收敛，`viewer/` 讲登录态与模型对比边界。

## 反模式

- 不要在 route 中直接 new 裸 `createServerClient()`（PKCE callback 特例除外，但它在 `app/auth/`）。
- 不要在 API payload 里直接返回整包数据库对象或上游异常。
- 不要绕过 `lib/comfyui-path.ts` / `lib/r2-url.ts` 手拼路径或图片 URL。
