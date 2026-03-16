# app/auth/ — Supabase Auth 回调特例

## 概览

- 当前目录只承载 OAuth / PKCE callback；它是 `app/` 里少数直接用 `@supabase/ssr` `createServerClient()` 的特例。

## 去哪儿看

| 场景             | 位置                               | 备注                                        |
| ---------------- | ---------------------------------- | ------------------------------------------- |
| OAuth 回调       | `callback/route.ts`                | 读取 `code` / `next`，交换 session 后重定向 |
| 浏览器端登录入口 | `components/auth-login-dialog.tsx` | 发起 OAuth provider 登录                    |
| 常规服务端鉴权   | `lib/supabase-auth.ts`             | 注意：callback 不走这里                     |

## 约定（本目录特有）

- `callback/route.ts` 保持 `runtime = "nodejs"`。
- 这里直接用 `createServerClient(url, anonKey, { cookies })` 做 PKCE session 交换；不要改成 `createSupabaseAuthClient()`。
- cookie 桥接统一通过 `next/headers` 的 `cookies()` 实现 `getAll()` / `setAll()`。
- 缺少 `code`、缺少 Supabase 环境变量、或 code exchange 失败时都回退为重定向；不要把 auth 细节暴露给用户。
- `next` 参数只作为重定向目标片段使用；最终始终回到当前 origin。

## 反模式

- 不要把 callback 写成页面组件或客户端组件。
- 不要在这里打印完整 session、token、环境变量。
- 不要引入与 OAuth callback 无关的页面状态或业务查询逻辑。
