# Tasks: 画师提示词收藏（Style Favorites）

> Plan：`tasks/plan.md` | 任务按依赖排序，逐个执行、逐个验证。

- [ ] **T1: DB migration —— `user_style_favorites` + `run_style_items`**
  - Acceptance: 两表建成；`user_style_favorites` 主键 `(user_id, style_key)`，RLS = own-row select/insert/update/delete + service_role 全通（照抄 `user_preferences` 完整模板含 update policy 并补 delete；upsert 的 ON CONFLICT DO UPDATE 依赖 update policy）；`run_style_items` 主键 `(run_id, style_key)`，`style_key` 索引，anon/authenticated 可 select、写仅 service_role；policy 幂等创建；`pnpm dlx supabase migration new add_style_favorites` 生成文件后填充。
  - Verify: 本地无 Supabase 栈，用一次性 Postgres 容器按序应用全部 migrations 干净通过；`\d+ public.user_style_favorites` / `pg_policies` 确认表与策略；重复执行幂等（CP1）。
  - Files: `supabase/migrations/YYYYMMDDHHMMSS_add_style_favorites.sql`

- [ ] **T2: 上传管线写入 `run_style_items`**
  - Acceptance: `supabase_writer.py` 在写 grid_items 的同一 run 上下文中，按 payload 已有的 `y_style_key`（`upload_planner.py:459-461`）upsert `run_style_items` 行 `(run_id, style_key, y_index, label=y_value)`；缺 `y_style_key` 的记录跳过不上报错；顺手删除 `tests/test_supabase_writer.py:159` 的 `run_y_prompt_refs` 死引用并补新表 fake。
  - Verify: `uv run pytest -q tests/test_supabase_writer.py` 绿；新增契约断言写入行内容。
  - Files: `scripts/r2_upload/supabase_writer.py`、`tests/test_supabase_writer.py`

- [ ] **T3: 历史 run 回填脚本（确定性重放）**
  - Acceptance: `scripts/other/backfill_run_style_items.py` 对每个 DB 中存在的 run：读 `outputs/<run>/run.json` 的 `y_json_path` / `y_json_sha256`，按 hash 解析当时版本 Y 资产（当前文件不符则从 git 历史按 sha256 找回）；`yaml.safe_load` 最小解析 `items[].info.index` + 顶层 `collection_id`（**不用 `read_y_rows`**，它硬校验 v3 而老资产是 v2）；按 `items[y_index].info.index` 生成 `style_key`，label 取 metadata `y_value`；校验 metadata distinct `y_index` == `selection.y_indexes` 集合；幂等 upsert `run_style_items`；失败 run 报错跳过并明示；支持 `--dry-run`；运行开始先打印 DB runs × 本地 outputs 覆盖矩阵（每个 run 将回填/跳过及原因；2026-07-17 已核实 6/6 全覆盖，`_old` 目录不参与）。
  - Verify: `uv run pytest -q tests/test_backfill_run_style_items.py` 绿（CP2，连同全套 pytest）。
  - Files: `scripts/other/backfill_run_style_items.py`、`tests/test_backfill_run_style_items.py`

- [ ] **T4: 共享类型 + style-items API**
  - Acceptance: `lib/style-favorites.ts` 定义 `StyleKey`、`StyleItem { y_index, style_key }` 等类型与 type guard；`GET /api/comfyui/run/[runDir]/style-items` 返回 `[{ y_index, style_key }]`（0-based），`runDir` 先过 `isValidRunDir()`，公开可读，`runtime = "nodejs"`，错误固定短文案。
  - Verify: `pnpm dev` 下 curl 已回填 run 返回 200 且形态正确；无效 runDir 返回 400/404；`pnpm lint` 绿。
  - Files: `lib/style-favorites.ts`、`app/api/comfyui/run/[runDir]/style-items/route.ts`

- [ ] **T5: 收藏 API（GET / PUT / DELETE）**
  - Acceptance: `GET /api/viewer/style-favorites` 返回 `{ favorites: [{ style_key, label, created_at, runs: [{ run_dir, name, y_index }] }] }`（先按 style_key 集反查 `run_style_items`，再按 `run_dir` 关联 `run_list_items.model_name`——`runs` 表无 name 列，已核实）；`PUT` body `{ style_key, label }` upsert（body 校验：`style_key` 匹配 `^[^:]+:\d+$` 且 ≤200 字符、`label` 非空且 ≤1000 字符——实测最长 y_value = 467，不满足 400）；`DELETE /api/viewer/style-favorites/[styleKey]` 删除（styleKey 含 `:`，客户端必须 `encodeURIComponent`）；未登录一律 401 `Authentication required`；坏 body 400。
  - Verify: dev server + 测试账号 curl 完成 PUT→GET→DELETE 闭环（CP3）。
  - Files: `app/api/viewer/style-favorites/route.ts`、`app/api/viewer/style-favorites/[styleKey]/route.ts`、`lib/style-favorites.ts`（补响应 guard）

- [ ] **T6: 客户端数据层（lib 薄函数 + 网格 hook）**
  - Acceptance: `hooks/AGENTS.md` 禁止页面级业务数据 hook，故拆分：`lib/style-favorites.ts` 放类型/guard + `fetchStyleFavorites()` / `upsertStyleFavorite()` / `deleteStyleFavorite()` 薄函数（fetch 模式仿 `user-preferences-provider.tsx:64-84`）；`app/models/[runDir]/use-style-favorites.ts` 为网格 stateful hook，暴露 `{ favoriteKeys: Set<string>, toggle(styleKey, label), isLoading }`，toggle 乐观更新、失败回滚 + toast；收藏页组件内自包含拉取列表；`key={user?.id ?? "anonymous"}` 重置。
  - Verify: `pnpm lint` 绿；由 T7/T9 集成验证行为。
  - Files: `lib/style-favorites.ts`、`app/models/[runDir]/use-style-favorites.ts`、`messages/zh.json`、`messages/en.json`

- [ ] **T7: 行标签星标（Mixer + Legacy 两形态）**
  - Acceptance: `virtual-grid-row-label.tsx` 两种形态各加星标按钮，不挤压现有 Artist/Common 复制交互；星标对未登录用户同样渲染（点击弹 `AuthLoginDialog`），故 style-items 拉取**不限登录态**，在 bootstrap ready 后惰性拉取，失败静默隐藏星标；登录用户点击 toggle 收藏，状态即时反馈。
  - Verify: 手工浏览器核对两形态 UI 截图 + 点击行为；`pnpm lint` 绿。
  - Files: `components/comfyui/virtual-grid-row-label.tsx`、`components/comfyui/virtual-grid.tsx`

- [ ] **T8: 工具栏收藏面板（详情页内跳转）**
  - Acceptance: 工具栏新增收藏入口，面板按行号升序列出全部收藏（所有模型均用同一 Y 资产全量 432 项、用户确认无例外，收藏串必然在当前 run 中；保留防御性过滤）；label 摘要取当前 run 网格行标签（经 style-items 的 style_key↔y_index 映射客户端 join，不用收藏快照）；点击调用 `scrollToLineNumber()` 并 `syncUrlHashWithLineNumber()`；无收藏时空态文案；未登录入口点击弹登录框（与 T7 一致）。
  - Verify: 手工验证滚动落点与 URL hash；复跑现有 `task-13-hash-jump` e2e 确认无回归。
  - Files: `components/comfyui/virtual-grid.tsx`（如拆分则新增 `components/comfyui/grid-favorites-panel.tsx`）

- [ ] **T9: 收藏页 `/[locale]/favorites`**
  - Acceptance: 登录门控（未登录显示登录引导，参考 prompts 页门控）；列表按收藏时间倒序，每项显示 label、时间、可用模型（run 名称），点击模型跳 `/{locale}/models/{runDir}#{y_index + 1}`；每项可取消收藏；无可用的模型显示"暂无可用模型"；`generateMetadata` 用 `buildSeoMetadata()` 且 `robots: { index: false }`。
  - Verify: 手工浏览器验证 + e2e 未登录引导（T11）。
  - Files: `app/[locale]/favorites/page.tsx`、`components/favorites/favorites-page.tsx`、`middleware.ts`（`LOCALIZED_PATH_PATTERNS` 加 `/^\/favorites/`）

- [ ] **T10: 站点头部收藏入口**
  - Acceptance: 登录后 `SiteHeader` nav 显示收藏页链接（"Prompt 法典"旁），未登录不渲染；i18n 文案。
  - Verify: 手工验证两语言两登录态。
  - Files: `components/site-header.tsx`、`messages/zh.json`、`messages/en.json`

- [ ] **T11: e2e**
  - Acceptance: 第一步先做最小 spike：service-role admin `generate_link` + Playwright goto 验证能在远端（`email: false`）建立 session，被阻断则降级为未登录路径 e2e + curl 验已登录 API 并改写 spec 决策 13。通过后：global setup 用 `SUPABASE_SERVICE_ROLE_KEY` 确保专用测试用户存在（固定邮箱，create-or-update 幂等）→ `generate_link` → `page.goto(action_link)` 经应用 `/auth/callback` 建真实 session → `storageState()` 存 `test-results/`；global teardown 用 service role 清空该测试用户的收藏。用例：未登录路径（行标签星标点击弹登录框、`/{locale}/favorites` 显示登录引导）+ 已登录路径（收藏 toggle、面板跳转、收藏页渲染与跨模型跳转）。
  - Verify: `E2E_SERVER=start E2E_PORT=3001 pnpm test:e2e -- -g "task 14"` 绿。
  - Files: `e2e/task-14-style-favorites.spec.ts`（按需新增 fixture）

- [ ] **T12: 文档与终验**
  - Acceptance: 更新根 `AGENTS.md`（结构表/去哪儿看/约定中的收藏功能条目）及触达目录的分层 `AGENTS.md`（`app/api`、`components/comfyui`、`hooks`、`scripts` 等）；spec 状态改为已实现；远端操作由用户主导，按发布顺序执行：远端 migration → 生产回填 → web 部署。
  - Verify: `pnpm lint` + `uv run pytest -q` + `pnpm test:e2e` 全绿（CP5）。
  - Files: `AGENTS.md` 及分层 `AGENTS.md`、`tasks/spec-style-favorites.md`
