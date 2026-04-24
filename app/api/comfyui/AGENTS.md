<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-04-25 -->

# app/api/comfyui/ — ComfyUI 数据查询 API（Node runtime）

## 概览

- 当前 ComfyUI API 已精简为三个核心 route：`runs`（首页列表）、`access`（媒体授权）、`workflow`（下载）。run 详情与 grid 数据不再通过独立 API route 返回，而是由前端直接拉取 R2 上的 view bootstrap JSON（`view/current.json` → `view/v2/{release_id}/bootstrap.*.json`）。
- 术语约定：展示页缩略图（`display_*` / `thumb_*`）出现在 view bootstrap JSON 中；首页封面图与主页缩略图则在 `runs` 列表的 `assets.cover` / `assets.homepage_cards` 字段中。

## 去哪儿看

| 场景          | 位置                                  | 备注                                                            |
| ------------- | ------------------------------------- | --------------------------------------------------------------- |
| runs 列表     | `runs/route.ts`                       | 通过 `lib/run-list.ts:listRunSummaries()` 查询 Supabase         |
| 媒体授权      | `run/[runDir]/access/route.ts`        | 认证用户获取 SFW/NSFW 视图 grant，由 `lib/run-media-grant.ts` 管理 |
| workflow 下载 | `run/[runDir]/workflow/route.ts`      | 验证 artifact key 后从 R2_PUBLIC_BUCKET 流式返回                |
| 公开对象代理  | `app/api/public-object/route.ts`      | R2 公开对象代理，直接回源                                       |
| 私有对象代理  | `app/api/private-object/route.ts`     | R2 私有对象代理，需 grant token 验证                            |

## 约定（本目录特有）

- 每个 `route.ts` 保持 `export const runtime = "nodejs"`。
- 服务端查询统一走 `createSupabaseAuthClient()`；使用 publishable key + cookie session，受 RLS 约束。
- 动态 route 统一采用 `context.params: Promise<{ runDir: string }>` 形态；进入 handler 后先 `await context.params`，再做 `isValidRunDir()` 校验。
- `runs/route.ts` 当前除基础字段外，还会返回首页列表所需的 `model`、`assets.cover` 与 `assets.homepage_cards`；这些字段用于首页封面图和主页缩略图展示。
- `access/route.ts` 负责分发 SFW/NSFW 视图的临时 grant token，供前端构造私有对象 URL。
- `workflow/route.ts` 先从 `runs.workflow_download_r2_key` 取 key，验证后通过 `getCloudflareContext().env.R2_PUBLIC_BUCKET` 回源。
- `catch` 分支只返回固定短文案，避免暴露数据库、路径、环境细节。

## 反模式

- 不要把这些 route 迁到 Edge runtime。
- 不要在 route 中直接创建裸 `createServerClient()` 或绕过 `lib/supabase-auth.ts`。
- 不要把异常 message、SQL 错误或本机路径原样回传给客户端。
- 不要为图方便把前端所需字段之外的整包数据库对象直接返回。
- 不要绕过 key 校验直接信任数据库里的 artifact key，也不要把完整 key/bucket 细节暴露给客户端。
