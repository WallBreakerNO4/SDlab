# Spec: 画师提示词收藏（Style Favorites）

> 状态：已实现（2026-07-17） | 日期：2026-07-17 | 分支：dev

## 背景与教训

本项目曾两次实现收藏功能，均被撤回：

1. **第一次（太简单）**：用行标签字符串做匹配，无法应对各种权重格式（`1.1::` / `:1.2` / 平方权重等），同一画师串不同渲染即匹配失败。
2. **第二次（`59676f2` → `178db0f` 撤回）**：DB 设计有改善，但迁移/落地方案不满意，整体放弃。

本设计针对两点教训：

- **身份用 `style_key`，不用字符串匹配**：`style_key = {collection_id}:{item_index}` 由 `scripts/generation/prompt_grid.py:221-237` 从 Y 轴 YAML 生成，跨 run 稳定，与权重渲染无关。注意：`y_style_key` 字段只在 `831569c` 之后生成的 run 的 `metadata.jsonl` 中存在（2026-07-17 验证：本地 8 个 run 中仅 `anima-base-1-arist-mixer` 全量含有），老 run 的迁移不依赖该字段，走确定性重放（见「数据流」）。
- **迁移方案从零重设计**：新增两张表 + 一个回填脚本，**不改现有表、不重传历史 run、不动 R2 manifest**。历史 run 的映射通过确定性重放回填：每个 run 的 `run.json` 记录了当时 Y 资产的路径与 sha256，可精确重建 `y_index → style_key` 位置映射（已验证老版 YAML `08eacc43…` 可从 git 历史 `318b983a` 找回）。

## Objective

登录用户可以：

1. 在模型详情页浏览时，对任意一行画师串（Y 轴条目，artists + general 整体）加星收藏 / 取消收藏。
2. 在当前模型详情页内，通过工具栏收藏面板快速滚动到自己收藏的画师串所在行（复用现有 hash 跳转）。
3. 在专属收藏页 `/[locale]/favorites` 查看全部收藏，并看到每个画师串在哪些模型中可用，点击跨模型跳转到对应模型的对应行。
4. 未登录用户点击收藏时弹出登录对话框；收藏页对未登录用户显示登录引导。

非目标（本期不做）：收藏分组/标签、收藏上限、收藏内搜索排序自定义、分享收藏列表。

## 技术方案概要

### 身份与匹配

- 收藏键：`style_key`（文本，如 `300-nai-styles-table:9`）。跨 run 匹配只比较 `style_key`，永不比较 prompt 字符串。
- `label`（行标签渲染串）仅作为显示快照随收藏一并存储，收藏页展示用；不参与匹配。用户已确认不会回改 YAML 权重，快照过期不作为问题处理。

### 数据库（一个新 migration，两表）

- `user_style_favorites`：`user_id uuid references auth.users(id) on delete cascade`、`style_key text`、`label text`、`created_at timestamptz default now()`；`primary key (user_id, style_key)`。RLS 照抄 `user_preferences` 完整模板（own-row select/insert/update，已核实模板含 update policy）并补 delete policy：own-row select/insert/update/delete + service_role 全通（upsert 的 ON CONFLICT DO UPDATE 分支依赖 update policy）；grants 对应。
- `run_style_items`：`run_id uuid references runs(id) on delete cascade`、`run_dir text not null`（沿用投影表惯例冗余 `run_dir`，与 `run_grid_items` 等表一致）、`style_key text`、`y_index int`、`label text`；`primary key (run_id, style_key)`；`style_key` 上建索引（反查：收藏 → 哪些 run 包含）。RLS：anon/authenticated 可读（与网格数据同级的公开元数据），写仅 service_role。
- policy 写法沿用现有幂等模式（`do $$ ... if not exists (select from pg_policies)`）；远端有 `rls_auto_enable()` trigger，policy 仍需显式创建。

### 数据流

- 新 run 上传：`scripts/r2_upload/supabase_writer.py` 在上传时顺带写入 `run_style_items`（数据来自上传 payload 中已有的 `y_style_key` 字段）。
- 历史 run 回填：`scripts/other/` 下新增一次性脚本，按 run_dir 匹配 `runs` 表后做确定性重放——读 `outputs/<run>/run.json` 的 `y_json_path` / `y_json_sha256`，按 hash 解析该 run 当时使用的 Y 资产（当前文件 hash 不符时从 git 历史找回匹配 sha256 的版本），**最小解析**（`yaml.safe_load`，只取 `items[].info.index`；`collection_id` 复刻 `prompt_grid.py:_y_collection_id` 逻辑——顶层 `collection_id` 缺失时回退规范化文件名 stem，当前 v3 资产即无顶层键、实际用 stem `300-nai-styles-table`；不走 `read_y_rows`——它硬校验 `prompt-y-table/v3`，老资产是 v2，`prompt_grid.py:167-169`）。`metadata.jsonl` 的 `y_index` 语义为 YAML items 原始索引（`runner_coordinator.py:232`），故映射即 `items[y_index].info.index → style_key`；label 取 `y_value`。校验：metadata distinct `y_index` 集合必须等于 `run.json` 记录的 `selection.y_indexes` 集合。全程不做字符串匹配；hash 无法解析或校验失败的 run 报错跳过并明示原因。本地没有产物的 run 不回填，等下次重传自然补齐。（2026-07-17 复核验证：8 个本地 run 的 `selection.y_indexes` 均为连续 0..431，老版 YAML 恰有 432 个带 `info.index` 的 item，闭环吻合。）
- Web 端**不**改 bootstrap / row manifest，不重传 R2。

### API（全部 `runtime = "nodejs"`，固定短错误文案）

- `GET /api/viewer/style-favorites`：返回当前用户收藏列表，每项含 `style_key`、`label`、`created_at`、`runs: [{ run_dir, name, y_index }]`（按 style_key 集反查 `run_style_items`，再按 `run_dir` 关联 `run_list_items.model_name` 得显示名——`runs` 表本身无 name 列，已核实）。未登录 401。
- `PUT /api/viewer/style-favorites`：body `{ style_key, label }`，upsert。未登录 401。
- `DELETE /api/viewer/style-favorites/[styleKey]`：删除。未登录 401。
- `GET /api/comfyui/run/[runDir]/style-items`：返回该 run 的 `[{ y_index, style_key }]`（网格行收藏态 + 跳转用），公开可读，`runDir` 先过 `isValidRunDir()`。
- 鉴权统一 `createSupabaseAuthClient()` + `requireViewerForPreferenceWrite()` 同款 `getUser()` / `"UNAUTHENTICATED"` 约定。

### 前端

- **行标签**（`components/comfyui/virtual-grid-row-label.tsx`）：两种形态（Mixer / Legacy）各加一个星标按钮，不改变现有复制交互；未登录点击 → 弹 `AuthLoginDialog`（现有按需弹窗模式）。
- **工具栏收藏面板**（`virtual-grid.tsx`）：登录后工具栏增加收藏入口，按行号升序列出收藏的画师串，点击 → 复用 `scrollToLineNumber()` + `syncUrlHashWithLineNumber()` 滚动并更新 hash。所有模型生图均使用同一 Y 资产（`data/prompts/Y/300_NAI_Styles_Table.yaml`，432 项全量选择，2026-07-17 用户确认无任何例外），收藏串必然存在于当前 run 且 `y_index + 1` 恒等于网格行号，面板不做"本模型包含 N/M"之类区分（仅保留防御性过滤：未来 Y 资产变更时自动跳过不存在的项）。面板 label 取当前 run 网格行标签（经 style-items 映射客户端 join），不用收藏快照。
- **收藏页**（`app/[locale]/favorites/page.tsx` + `components/`）：登录门控（参考 prompts 页门控模式）；列出收藏（label、收藏时间、可用模型列表），点击模型 → `/{locale}/models/{runDir}#{y_index + 1}`（hash 为 1 起始行号，现有机制直接消费）。每项可取消收藏。
- **站点头部**：登录后显示收藏页入口链接。
- **状态**：`lib/style-favorites.ts` 放类型/guard + 薄 fetch/mutate 函数（参考 `user-preferences-provider.tsx` 的 fetch 模式与 `key={user?.id ?? "anonymous"}` 重置）；网格 stateful hook 放 `app/models/[runDir]/use-style-favorites.ts`（`hooks/` 目录约定不放业务数据 hook）；网格的 style-items 映射在 bootstrap ready 后惰性拉取（不限登录态，未登录也渲染星标、点击弹登录框），失败静默降级（不阻塞网格）。
- **i18n**：`messages/zh.json` / `en.json` 新增对应 namespace。

## Tech Stack

Next.js 16 + React 19 + next-intl + Supabase SSR（既有）；Python 3.13 + uv（上传/回填侧）。无新依赖。

## Commands

```bash
# Web
pnpm dev
pnpm lint

# Python 测试
uv run pytest -q

# E2E
pnpm test:e2e
E2E_SERVER=start E2E_PORT=3001 pnpm test:e2e -- -g "<相关 spec>"

# Supabase 迁移
pnpm dlx supabase migration new add_style_favorites
pnpm dlx supabase db reset   # 本地验证
```

## Project Structure（新增/改动文件归属）

```
supabase/migrations/YYYYMMDDHHMMSS_add_style_favorites.sql   # 两表 + RLS
app/api/viewer/style-favorites/route.ts                       # GET / PUT
app/api/viewer/style-favorites/[styleKey]/route.ts            # DELETE
app/api/comfyui/run/[runDir]/style-items/route.ts             # y_index ↔ style_key
lib/style-favorites.ts                                        # 类型 + type guard + 薄 fetch/mutate 函数
app/models/[runDir]/use-style-favorites.ts                    # 网格侧 stateful hook（hooks/ 不放业务数据 hook）
app/[locale]/favorites/page.tsx                               # 收藏页（服务端壳 + metadata）
components/favorites/favorites-page.tsx                       # 收藏页客户端 UI（含登录门控）
middleware.ts                                                 # LOCALIZED_PATH_PATTERNS 增加 /favorites
components/comfyui/virtual-grid-row-label.tsx                 # 行标签星标
components/comfyui/virtual-grid.tsx                           # 工具栏收藏面板
components/site-header.tsx                                    # 收藏页入口
messages/zh.json, messages/en.json                            # i18n
scripts/r2_upload/supabase_writer.py                          # 上传写 run_style_items
scripts/other/backfill_run_style_items.py                     # 历史回填
tests/                                                        # pytest：writer + 回填 + API 侧类型
e2e/                                                          # 收藏 toggle / 收藏页 / 跨模型跳转
```

## Code Style

遵循现有约定，照抄最近邻文件的模式，例如 API route：

```ts
export const runtime = "nodejs";

export async function PUT(request: NextRequest) {
  const body = parseUpsertBody(await request.json());
  if (!body) return jsonError(400, "Invalid style favorite payload");
  const supabase = await createSupabaseAuthClient();
  try {
    const user = await requireViewerForPreferenceWrite(supabase);
    // ... upsert，RLS 保证只写自己的行
  } catch (error) {
    if (error instanceof Error && error.message === "UNAUTHENTICATED") {
      return jsonError(401, "Authentication required");
    }
    return jsonError(500, "Failed to update style favorite");
  }
}
```

关键约定：路径/URL 走 `lib/comfyui-path.ts` / `lib/r2-url.ts`；`runDir` 先过 `isValidRunDir()`；错误消息固定短文案不透内部细节；i18n 文案进 `messages/*.json` 不硬编码；协作文档与注释用中文。

## Testing Strategy

- **pytest**（`tests/`）：
  - `supabase_writer.py` 写入 `run_style_items` 的契约测试（沿用 fake Supabase client 模式；顺手清理 `tests/test_supabase_writer.py:159` 的 `run_y_prompt_refs` 死引用）。
  - 回填脚本：fixture run.json + metadata.jsonl + 两版 YAML 资产 → 重放出正确 `y_index → style_key` 映射与 upsert 行；hash 无法解析 / 条目数不符时安全跳过。
- **e2e**（`e2e/`，Playwright）：沿用 mock-run fixture 模式 —— 行标签收藏 toggle（含未登录弹登录框）、工具栏面板跳转、收藏页渲染与跨模型跳转。已登录态：service-role admin 链路建专用测试用户 + `generate_link` 经应用 `/auth/callback` 建立真实 session（详见决策记录 13）。
- 验证命令：`uv run pytest -q`、`pnpm lint`、`pnpm test:e2e`。

## Boundaries

- **Always**：迁移幂等可重放；RLS policy 显式创建；新 API 先验证请求体再鉴权；`pnpm lint` + `uv run pytest -q` 通过后才算任务完成。
- **Ask first**：改 `package.json` / `pyproject.toml` 依赖；改既有表结构；远端 migration 执行（`supabase db push` 或等价操作）；对历史 run 做任何重传/force-publish。
- **Never**：用 prompt 字符串/label/prompt_hash 做跨 run 匹配；改 R2 bootstrap/row manifest 格式并重传历史 run；把 Supabase 凭证、内部路径写进错误消息或日志；删测试或放宽断言过测；自行 `dev` → `main` 合并。

## Success Criteria

1. 登录用户在 mixer run 与普通 run 的行标签上都能收藏/取消，状态即时反馈，刷新后保持。
2. 同一 `style_key` 在不同 run 中即使渲染权重不同也正确匹配（测试构造同一 YAML 条目两种权重渲染的 metadata）。
3. 工具栏收藏面板点击条目 → 网格滚动到对应行且 URL hash 同步。
4. `/zh/favorites` 与 `/en/favorites`：未登录显示登录引导；登录后列出收藏及可用模型，点击跳转 `/{locale}/models/{runDir}#{line}` 并滚动到位；可取消收藏。
5. 收藏的串在当前 run 不存在时：面板/收藏页中该项显示为"当前模型不包含"（或不出现在详情页面板），不报错。
6. 新上传 run 自动有 `run_style_items`；回填脚本可对历史 run 幂等回填（重复执行不产生重复行）。
7. `uv run pytest -q`、`pnpm lint` 全绿；新增 e2e 通过。

## 评审决策记录（2026-07-17 grilling）

1. **回填存在性**：保留。上次失败的问题是"本地没有全部 outputs"，本次已核实 DB 6 个 run 与本地 outputs 6/6 对应（`_old` 目录为同 run_dir 旧代际，不单独对应 DB run，不参与回填）。T3 含 pre-flight 覆盖核对。
2. **发布顺序**：远端 migration → 生产回填（service role，用户主导执行）→ web 部署。
3. **空窗期**：回填耗时短（6 run × 432 行），不做特殊文案。
4. **面板语义**：所有模型共用同一 Y 表全量 432 项，收藏串必然存在于当前 run；面板列出全部收藏，不做"包含 N/M"区分。
5. **label 快照**：直接显示快照；用户确认不会回改 YAML 权重，快照过期不作问题处理。
6. **性能**：style-items 不加缓存（MVP 直接接受每详情页 +1~2 请求），有真实数据后再议。
7. **e2e**：优先覆盖已登录路径；第一轮设想的"本地 supabase + 种子测试用户"前提不成立（本项目无本地 Supabase，全部在远端），已在第二轮决策 13 重新设计。
8. **CP4 手工验证**：用户本人执行。

## 评审决策记录（2026-07-17 grilling 第二轮）

9. **RLS update policy**：`user_style_favorites` RLS 为 own-row select/insert/**update**/delete + service_role 全通；已核实 `user_preferences` 模板含 update policy（`supabase/migrations/20260405110049_add_user_nsfw_preference.sql:47-54`），照抄完整模板并补 delete；upsert 的 ON CONFLICT DO UPDATE 分支依赖 update policy，不允许改用 ignoreDuplicates 回避。
10. **PUT 输入校验**：`style_key` 必须匹配 `^[^:]+:\d+$` 且长度 ≤ 200；`label` 非空且 ≤ 1000 字符（实施时实测现有 432 行最长 y_value = 467 字符，500 上限余量不足故放宽，DB 约束同值）；不满足一律 400。
11. **Y 资产唯一性假设成立**：所有模型生图均使用 `data/prompts/Y/300_NAI_Styles_Table.yaml` 全量 432 项（用户确认无任何例外），故 `y_index + 1` 恒等于网格行号，跨模型/面板跳转不处理部分选择情形；仅保留防御性过滤应对未来 Y 资产变更。
12. **label 双源**：详情页收藏面板取当前 run 网格行标签（style_key↔y_index 映射客户端 join，所见即所得）；收藏页用 `user_style_favorites.label` 快照（决策 5 不变）。style-items API 维持只返回 `[{ y_index, style_key }]`。
13. **e2e 已登录态（替代决策 7 原方案）**：本项目无本地 Supabase，e2e dev server 直连远端。global setup 用 `SUPABASE_SERVICE_ROLE_KEY` 调 admin API 确保专用测试用户存在（固定邮箱，create-or-update 幂等，全库仅一个测试用户）→ `POST /auth/v1/admin/generate_link`（type `magiclink`）→ **手工 follow verify（`redirect: "manual"`）从 Location fragment 截取 access_token/refresh_token**（远端 magiclink 走 implicit 流而非 PKCE；`redirect_to` 白名单不含本地地址，手工截取同时绕开该限制）→ 按 `@supabase/ssr` 0.8 实际编码构造 cookie（`sb-<ref>-auth-token`，`base64-` + base64url(JSON session)，3180 字符分块）注入浏览器上下文 → `storageState()` 存 `test-results/`（已 gitignore）供已登录用例复用；global teardown 用 service role 清空该测试用户的 `user_style_favorites`。不开 email provider、不改远端 Auth 配置、仓库不留测试凭证。测试写入被 RLS 锁死在测试用户行内；`run_style_items` 全程只读。已核实远端 `email` provider 关闭、`disable_signup=false`（2026-07-17 `/auth/v1/settings`）。**2026-07-17 spike 已验证全链路**（createUser 幂等 422 → generate_link 200 → fragment 截取 → cookie 注入 → 已登录 API 200；含重复 PUT 的 UPDATE 分支），脚本在 `test-results/cp3-spike/spike.mjs`，T11 将其固化为 global setup。用户已确认同意在远端创建/复用该测试用户。

## Open Questions

1. 收藏页可用模型列表是否需要封面缩略图？（默认：纯文本 run 名称列表，保持轻量；如要封面则复用首页卡片资源约定。）
2. 行标签星标在 Mixer 形态（已有 Artist/Common 两个复制按钮）中的摆放位置，实施时以不挤压现有交互为准，必要时先做 Legacy 形态。

## 实施记录（2026-07-17）

- **CP1（migration 验证）**：本地无 Supabase 栈（全部在远端），改用一次性 Postgres 容器按序应用全部 migrations 干净通过：两表 + policies + grants 齐备、迁移链无冲突、重复执行幂等。
- **CP3（API curl 闭环）**：dev server 下用 service-role admin 链路（generate_link + 手工截 fragment token + `@supabase/ssr` cookie 编码注入）完成 curl 验证：未登录 401、坏 body 400、PUT→GET→DELETE 闭环正确，重复 PUT 的 ON CONFLICT DO UPDATE 分支亦覆盖。
- **生产回填已执行**：`scripts/other/backfill_run_style_items.py` 对 6 个 run 各回填 432 行（6×432），幂等复跑结果一致。
- **CP5（终验口径）**：`pnpm lint`、`pnpm typecheck`、`uv run pytest -q` 全绿；e2e task-14 8/8 绿（`E2E_SERVER=start` + 默认 3000 端口）；全量 e2e 套件另有 7 个失败均为陈旧 spec（首页链接选择器未含 locale 前缀、mock 旧 `/api/comfyui/image` 代理/旧 run API 路径、环境敏感用例），与本功能无关、base 上即失败；用户已决定（2026-07-17）陈旧 spec 修复另立 hygiene 任务，不在本分支处理。
- **`playwright.config.ts` baseURL 改 `localhost`**：R2 CORS 只放行 `http://localhost:3000` 与生产域名，`127.0.0.1` 会被 CORS 拒且 dev 模式下不 hydrate；start 模式 e2e 因此必须用默认 3000 端口。
