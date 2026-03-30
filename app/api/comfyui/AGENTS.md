# app/api/comfyui/ — ComfyUI 数据查询 API（Node runtime）

## 概览

- 这里既有 JSON 查询 API，也有 workflow 下载 route：`runs`、`run detail`、`grid`、`row`、`workflow`。查询数据主要来自 Supabase，workflow 文件通过 Cloudflare R2 返回下载响应。
- 术语约定：`row/route.ts` 与 `grid/route.ts` 暴露的 `display_*` / `thumb_*` 变体统一称为“展示页缩略图”；未来首页卡片若引入独立图片资源，应称为“主页缩略图”，并通过单独字段或接口输出。

## 去哪儿看

| 场景           | 位置                             | 备注                                                      |
| -------------- | -------------------------------- | --------------------------------------------------------- |
| runs 列表      | `runs/route.ts`                  | 读取 `runs` 表并收敛 summary                              |
| run 详情       | `run/[runDir]/route.ts`          | 返回 run 基础信息 + x/y labels + `x_columns`/`y_indexes`  |
| grid 索引      | `run/[runDir]/grid/route.ts`     | 返回 `blurhash_cells`，按页规避 PostgREST `max_rows`      |
| row 级图片查询 | `run/[runDir]/row/route.ts`      | 返回每个 cell 的展示页缩略图 URL（display/thumb）         |
| workflow 下载  | `run/[runDir]/workflow/route.ts` | 校验 workflow artifact key 后从 R2_PUBLIC_BUCKET 流式返回 |

## 约定（本目录特有）

- 每个 `route.ts` 保持 `export const runtime = "nodejs"`。
- 服务端查询统一走 `createSupabaseAuthClient()`；使用 publishable key + cookie session，受 RLS 约束。
- `runDir` 入口先用 `isValidRunDir()` 判形态；非法值直接 404，不继续查库。
- 对外 payload 只保留前端渲染需要的字段；不要透传原始 `run_json` / `metadata` 大对象。
- `grid/route.ts` 需要分页拉 `images`，否则会撞 PostgREST 默认 `max_rows`。
- `row/route.ts` 负责把 `image_variants` 映射成展示页缩略图 URL（display/thumb）；公开/私有 URL 都通过 `lib/r2-url.ts`。
- `workflow/route.ts` 先从 `runs.workflow_download_r2_key` 取 key，再验证它必须落在 `runs/{runDir}/artifacts/workflow/*.json`，随后通过 `getCloudflareContext().env.R2_PUBLIC_BUCKET` 回源并保留对象 metadata。
- `catch` 分支只返回固定短文案，避免暴露数据库、路径、环境细节。

## 反模式

- 不要把这些 route 迁到 Edge runtime。
- 不要在 route 中直接创建裸 `createServerClient()` 或绕过 `lib/supabase-auth.ts`。
- 不要把异常 message、SQL 错误或本机路径原样回传给客户端。
- 不要为图方便把前端所需字段之外的整包数据库对象直接返回。
- 不要绕过 `isValidWorkflowArtifactKey()` 信任数据库里的 workflow key，也不要把完整 key/bucket 细节暴露给客户端。
