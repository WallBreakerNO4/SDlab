# app/api/ — App Router API 共性约定

## 概览

- 本目录放 Web 侧服务端 route：当前主要是 ComfyUI JSON 查询 API；子目录只补充各自 payload 细节。

## 去哪儿看

| 场景             | 位置                                   | 备注                                      |
| ---------------- | -------------------------------------- | ----------------------------------------- |
| API 共性入口     | `app/api/` 下各 `route.ts`             | 统一 Node runtime、短错误响应、服务端鉴权 |
| ComfyUI API 细则 | `app/api/comfyui/AGENTS.md`            | runs / detail / grid / row                |
| 共享鉴权客户端   | `lib/supabase-auth.ts`                 | `createSupabaseAuthClient()`              |
| 路径与 URL 边界  | `lib/comfyui-path.ts`、`lib/r2-url.ts` | 参数校验与 URL 生成入口                   |

## 约定（本目录特有）

- route 统一保持 `export const runtime = "nodejs"`；不要把本目录迁到 Edge runtime。
- 需要用户态的 route 统一走 `createSupabaseAuthClient()`；`app/auth/callback/route.ts` 不属于本目录里的共性约束。
- 对外错误响应保持固定短文案；不要透出 SQL、路径、bucket、凭证、堆栈。
- 进入查询前先校验输入：`runDir` 先做 type guard；不要在 route 内自由拼接路径或对象 key。
- 子目录文档优先级高于本文件：`comfyui/` 讲 payload 收敛。

## 反模式

- 不要在 route 中直接 new 裸 `createServerClient()`（PKCE callback 特例除外，但它在 `app/auth/`）。
- 不要在 API payload 里直接返回整包数据库对象或上游异常。
- 不要绕过 `lib/comfyui-path.ts` / `lib/r2-url.ts` 手拼路径或图片 URL。
