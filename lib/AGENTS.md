# lib/ — Node 侧共享边界（Supabase + R2 + 路径安全 + 类型）

## 概览

- `lib/` 是 Web 侧共享边界层：认证态 Supabase 客户端、R2 URL 构建、路径安全、共享类型和 `cn()` 工具都在这里。

## 去哪儿看

| 场景                       | 位置                  | 备注                                             |
| -------------------------- | --------------------- | ------------------------------------------------ |
| 服务端 Supabase 客户端     | `supabase-auth.ts`    | `server-only` + cookie session + publishable key |
| 浏览器端 Supabase 客户端   | `supabase-browser.ts` | `AuthProvider` 使用                              |
| Supabase 相关类型          | `supabase-types.ts`   | run/image/variant 与 JSON 类型                   |
| R2 URL 构建                | `r2-url.ts`           | `publicObjectUrl()` / `privateObjectUrl()`       |
| runDir 共享工具 / 路径校验 | `comfyui-path.ts`     | allowlist、相对路径、防逃逸                      |
| Web 领域类型               | `comfyui-types.ts`    | `RunSummary` / `RunDir` / type guard             |
| className 合并             | `utils.ts`            | `cn()`                                           |

## 约定（本目录特有）

- ComfyUI API route 统一使用 `createSupabaseAuthClient()`；它依赖 `server-only` 与 `next/headers`。
- 浏览器端认证统一使用 `createSupabaseBrowserClient()`；不要在客户端自己拼 Supabase SSR 初始化。
- `middleware.ts` 是例外：因为运行在 Edge，不能 import `lib/supabase-auth.ts`，只能内联建 client。
- `publicObjectUrl()` 和 `privateObjectUrl()` 都只允许 display/thumb 变体；这些 URL 服务的是“展示页缩略图”，不是未来首页卡片的“主页缩略图”。
- `privateObjectUrl()` 负责生成私有对象的短期签名 URL；签名的前置鉴权发生在 ComfyUI API 返回图片元数据时。
- API 侧 `runDir` 形态判断当前主要走 `comfyui-types.ts:isValidRunDir()`；`comfyui-path.ts` 更偏共享路径安全与 allowlist 工具。

## 反模式

- 不要在 route/组件中绕过本目录直接拼磁盘路径、R2 URL 或代理 URL。
- 不要把 `supabase-auth.ts` 导入客户端组件；它是 `server-only`。
- 不要放宽 `runDir` / `imagePath` 校验来“临时兼容”坏数据。
- 不要把包含路径、bucket、环境变量的信息原样透传给 API 响应。
