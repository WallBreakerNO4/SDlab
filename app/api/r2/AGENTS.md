# app/api/r2/ — R2 私有对象代理

## 概览

- 本目录只处理站内 R2 代理；当前是私有 bucket 读取入口，不承载 ComfyUI 业务查询。

## 去哪儿看

| 场景           | 位置                          | 备注                                         |
| -------------- | ----------------------------- | -------------------------------------------- |
| 私有对象代理   | `private/[...r2Key]/route.ts` | `GET` / `HEAD`，鉴权后代理 R2 private bucket |
| 共享鉴权客户端 | `lib/supabase-auth.ts`        | 统一 cookie session + RLS 身份               |
| R2 URL 构建    | `lib/r2-url.ts`               | 由 `privateObjectUrl()` 生成站内代理路径     |

## 约定（本目录特有）

- route 保持 `export const runtime = "nodejs"`，并显式 `dynamic = "force-dynamic"`。
- 只接受 `GET` / `HEAD`；其余方法直接 405，不在这里扩展写操作。
- 进入 R2 前先做鉴权：统一调用 `createSupabaseAuthClient()` 检查当前用户。
- `r2Key` 必须先过 segment decode + 校验；仅允许 `runs/` 前缀，以及 `display_*` / `thumb_*` 这些展示页缩略图变体命名。
- 代理响应要保留 R2 metadata / ETag / range / conditional request 语义；错误响应只返回固定短文案。
- 日志只打印脱敏后的 key 摘要（`hash12`），不要输出完整对象 key。

## 反模式

- 不要绕过 `decodeAndValidateSegments()` / `validatePrivateImageKey()` 直接信任 URL 片段。
- 不要把 bucket 名、完整 key、绝对路径或上游异常原样回传给客户端。
- 不要把本目录迁到 Edge runtime，也不要直接创建裸 `createServerClient()`。
- 不要在这里混入公开 R2 URL 拼接逻辑；公开/私有 URL 的入口仍在 `lib/r2-url.ts`。
