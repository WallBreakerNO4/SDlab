<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-25 | Updated: 2026-04-25 -->

# lib/env/ — 环境变量读取

## 概览

- 把 Supabase/R2 相关的环境变量读取集中管理，提供公共环境与仅服务端环境的缓存读取函数。

## 去哪儿看

| 场景                  | 位置           | 备注                                                                         |
| --------------------- | -------------- | ---------------------------------------------------------------------------- |
| 公共环境变量读取      | `public.ts`    | `getPublicEnv()`：`NEXT_PUBLIC_SUPABASE_URL` / `PUBLISHABLE_KEY` / `R2_PUBLIC_BASE_URL` |
| 仅服务端环境变量      | `server.ts`    | `getServerEnv()`：继承 `getPublicEnv()` + `RUN_MEDIA_GRANT_SECRET`           |
| Supabase 客户端初始化 | `lib/supabase-auth.ts`、`lib/supabase-browser.ts` | 消费 `getPublicEnv()` / `getServerEnv()`                    |
| R2 URL 构建           | `lib/r2-url.ts` | 消费 `r2PublicBaseUrl`                                                       |

## 约定（本目录特有）

- `public.ts` 读取的变量均以 `NEXT_PUBLIC_` 前缀，也可在服务端 fallback 到无前缀版本。
- `server.ts` 标记 `import "server-only"`，不能在客户端组件中导入。
- 两个模块均使用模块级缓存（`let cachedPublicEnv` / `let cachedServerEnv`），避免重复读取 `process.env`。
- 变量缺失时抛出明确的 `Missing required environment variable` 错误。
- `getServerEnv()` 内部调用 `getPublicEnv()` 避免重复定义。

## 反模式

- 不要在各个模块中直接 `process.env.XXX` 读取环境变量；统一走这里的 `getPublicEnv()` / `getServerEnv()`。
- 不要把 `server.ts` 导入客户端组件。
- 不要把这些读取函数当运行时配置传递敏感值到 API 响应。
