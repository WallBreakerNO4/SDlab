<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-07-20 | Updated: 2026-07-20 -->

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
| 对比 slice | `style-comparison/slice/route.ts` | 最多 40 个 style keys / 12 个 run dirs；返回 placements + grants |
| 请求/响应 guard | `lib/style-comparison.ts` | 游标、limit、slice body、响应结构与 viewer variant |
| 模型目录缓存 | `lib/style-comparison-server.ts` | `unstable_cache` 5 分钟，tag `style-comparison-models` |

## 约定（本目录特有）

- 所有 route 保持 `runtime = "nodejs"`，登录态统一通过 `createSupabaseAuthClient()` + `requireViewerForPreferenceWrite()` 获取；不要在 route 中创建裸服务端 client。
- 对比目录使用 `(created_at, style_key)` keyset cursor，`limit` 默认 40 且最大 40；只有首屏响应携带 `models`，后续页只返回收藏与 `next_cursor`。
- slice body 必须同时包含 1–40 个合法 `style_key` 和 1–12 个合法 `run_dir`；先验证 runDir 形态和收藏归属，再查询 `run_style_items` / `run_view_index`。
- `run_style_items.y_index` 与响应 placement 一律 0-based；只有拼详情页网格 hash 时才允许转换为 1-based 行号。
- 模型目录只包含 `run_view_index` 中已发布的 run，并通过 `getCachedPublishedRuns()` 缓存 5 分钟；不要在每个分页请求重复查询模型目录。
- slice 根据 `sdslab_show_nsfw` cookie 选择 `auth_sfw` / `auth_nsfw`，为每个发布视图签发 24 小时 media grant；客户端不能自行生成 grant。
- 所有输入在数据库查询前收敛；对外错误保持固定短文案，401/404/400 与 500 分开，不返回 SQL、凭证或上游错误。

## 测试要求

- `tests/style-comparison.test.ts` 当前只覆盖 cursor、limit、slice body 边界、目录/详情 guards、viewer cookie 与 cache URL；不覆盖 slice response guard。
- `tests/style-favorites.test.ts` 当前只覆盖 `isStyleFavoriteLabel()`，不覆盖 style key/entry guard 或 fetch/mutate 合约。
- 修改 slice response 或客户端 merge/显隐/reconcile/flatten 逻辑时，应补对应 `pnpm test` 用例；修改 placement 逻辑时应明确覆盖 0-based `y_index`。
- 当前不要把单元测试描述成模型对比 E2E；若新增完整浏览器流程，应在 `e2e/` 单独落 spec。

## 依赖

### Internal

- `lib/supabase-auth.ts`、`lib/server-user-preferences.ts` - 登录态和偏好写入边界
- `lib/style-favorites.ts`、`lib/style-comparison.ts` - `style_key` 与对比 payload 合约
- `lib/style-comparison-server.ts` - 已发布模型目录缓存
- `lib/run-media-grant.ts` - 私有 row/图片访问授权

### External

- Supabase - 收藏、run placement、发布视图与模型目录数据源
- Next.js App Router - Node route handler 与 `unstable_cache`
