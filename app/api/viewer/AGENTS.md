<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-07-20 | Updated: 2026-08-23 -->

# app/api/viewer/ — 浏览者偏好、收藏与模型对比 API

## 概览

- 本目录承载浏览者相关的 Node route：NSFW 偏好、画师串收藏 CRUD，以及收藏画师串跨已发布模型的目录、详情和 slice 查询。
- 除 NSFW 偏好 GET 可从 cookie 返回默认值外，收藏与模型对比接口均要求有效 Supabase 登录态。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| NSFW 偏好 | `preferences/nsfw/route.ts` | GET 读 cookie；PATCH 鉴权写 `user_preferences` 并同步 cookie |
| 收藏列表/写入 | `style-favorites/route.ts` | GET 列表；PUT 校验后 upsert |
| 删除收藏 | `style-favorites/[styleKey]/route.ts` | DELETE；动态参数先 `await context.params` |
| 对比目录 | `style-comparison/route.ts` | keyset cursor；每页默认/最多 40，首屏附已发布模型目录 |
| 单收藏对比详情 | `style-comparison/[styleKey]/route.ts` | 返回收藏快照与已发布模型目录 |
| 对比 slice | `style-comparison/slice/route.ts` | 最多 40 个 style keys / 12 个 run dirs；鉴权后一次业务 RPC 返回 placements、BlurHash tuple 与 run metadata，Worker 本地签 grant |
| 请求/响应 guard | `lib/style-comparison.ts` | 游标、limit、slice body、RPC/HTTP 响应结构与 viewer variant |
| 模型目录缓存 | `lib/style-comparison-server.ts` | 缓存未命中时一次公共模型目录 RPC；`unstable_cache` 5 分钟，tag `style-comparison-models` |

## 约定（本目录特有）

- 所有 route 保持 `runtime = "nodejs"`，登录态统一通过 `createSupabaseAuthClient()` + `requireViewerForPreferenceWrite()` 获取；不要在 route 中创建裸服务端 client。
- 对比目录使用 `(created_at, style_key)` keyset cursor，`limit` 默认 40 且最大 40；只有首屏响应携带 `models`，后续页只返回收藏与 `next_cursor`。
- slice body 必须同时包含 1–40 个合法 `style_key` 和 1–12 个 canonical 小写 kebab-case `run_dir`；Worker 先鉴权并读取 NSFW cookie，再通过 `get_style_comparison_slice` 一次 RPC 在数据库内完成收藏归属、`run_style_items` placement、`run_grid_items.blurhash` 与 `run_view_index` metadata 查询。
- slice placement 的 `blurhashes` 使用按 `x_index`、`batch_index` 排序的紧凑 tuple `[[x_index, batch_index, blurhash], ...]`；数据库只处理 materialized 的当前请求集合，NSFW 关闭时不得聚合 `category = 'nsfw'`。共享 normalizer 在响应缺少 `blurhashes` 字段时补成空数组。
- `run_style_items.y_index` 与响应 placement 一律 0-based；只有拼详情页网格 hash 时才允许转换为 1-based 行号。
- 模型目录只包含 `run_view_index` 中已发布的 run；`get_style_comparison_models` 一次 RPC 聚合目录字段，`getCachedPublishedRuns()` 缓存 5 分钟。缓存命中不访问数据库。
- slice 根据 `sdslab_show_nsfw` cookie 选择 `auth_sfw` / `auth_nsfw`，在 Worker 内为每个发布视图签发 24 小时 media grant；签名密钥不得进入数据库，客户端也不能自行生成 grant。
- 所有输入在数据库查询前收敛；对外错误保持固定短文案，401/404/400 与 500 分开，不返回 SQL、凭证或上游错误。

## 测试要求

- `tests/style-comparison.test.ts` 覆盖 cursor、limit、slice body、RPC 响应/归属/placement guard、目录/详情 guards、viewer cookie、row manifest 兼容与 cache URL。
- `tests/style-comparison-rpc-migration.test.ts` 锁定 RPC 权限、40/12 数据库上限、materialized 有界集合、BlurHash/NSFW 过滤、Worker 单 RPC 边界与模型目录 300 秒缓存；修改查询链路时必须同步更新。
- `tests/style-favorites.test.ts` 只覆盖 `isStyleFavoriteLabel()`，不覆盖 style key/entry guard 或 fetch/mutate 合约。
- 修改 slice response 或客户端 merge/显隐/reconcile/flatten 逻辑时，应补对应 `pnpm test` 用例；修改 placement 逻辑时应明确覆盖 0-based `y_index`。
- 不要把单元测试描述成模型对比 E2E；完整浏览器流程在 `e2e/` 单独落 spec。

## 依赖

### Internal

- `lib/supabase-auth.ts`、`lib/server-user-preferences.ts` - 登录态和偏好写入边界
- `lib/style-favorites.ts`、`lib/style-comparison.ts` - `style_key` 与对比 payload 合约
- `lib/style-comparison-server.ts` - 已发布模型目录缓存
- `lib/run-media-grant.ts` - 私有 row/图片访问授权

### External

- Supabase - 收藏、run placement、发布视图与模型目录数据源
- Next.js App Router - Node route handler 与 `unstable_cache`
