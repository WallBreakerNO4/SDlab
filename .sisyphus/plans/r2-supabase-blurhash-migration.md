# 网站迁移到 R2 + Supabase（按行懒加载 + Blurhash，占位；预留未来登录）

## TL;DR
> **Summary**: 把 Next.js 网站的数据源从本地 `comfyui_api_outputs/` 切到 Supabase（元数据）+ Cloudflare R2（图片），网格按“行”懒加载图片元数据并用 blurhash 做占位；暂不做 OAuth 登录，但保留未来接入空间。
> **Deliverables**: Supabase/R2 数据源 API；VirtualGrid 改为按行拉取 + R2 URL；private 图片代理端点（无鉴权直通代理）；Playwright 回归；`documents/` 部署与实现文档；分阶段中文 commit。
> **Effort**: Large
> **Parallel**: YES - 3 waves
> **Critical Path**: Supabase client + API 契约 → VirtualGrid 懒加载改造 → private 代理端点（无鉴权） → E2E + 文档

## Context
### Original Request
- 现在网站图片都在本地且无登录；先实现：从本地迁移到 R2 图片 + Supabase 元数据，支持 blurhash 占位；暂不实现登录。
- 图片层级：`original_png`（仅下载、需登录）/ `display_(avif|webp)`（大图）/ `thumb_(avif|webp)`（半分辨率缩略图）。
- 图片列类别：`normal`/`advance`/`nsfw`；本阶段不做登录/鉴权，仅打通链路（Supabase 元数据 + R2 public 直链 + R2 private 通过代理）。
- public 桶直链；private 桶通过 Worker/代理访问。
- blurhash 不需要 SSR 内嵌到 HTML；图片元数据按需加载（滚动时请求），不要首次拉全量。
- 每个阶段有进展就 git commit（中文）；列出新增依赖；安装依赖只允许 `pnpm add`；严禁读写 `.env`（只改 `.env.example`）；完成后在 `documents/` 留详细 Markdown。

### Interview Summary
- 当前目标优先打通全链路：Supabase 元数据（含 blurhash）→ public 直链显示 → private 通过代理/Worker 显示；登录/鉴权留到未来。
- 明确：本阶段不引入任何 cookie/header 级别的鉴权逻辑；private 代理端点先做“无鉴权直通”。
- 懒加载粒度：按单行（y_index）加载。

### Metis Review (gaps addressed)
- 补齐：前端缺少 Supabase/blurhash 依赖；避免用 Next `middleware.ts` 做代理（Next 16 更名为 `proxy.ts` 且官方建议尽量避免）。

## Work Objectives
### Core Objective
- 在不引入真实 OAuth 登录的前提下，把网站“图片展示”与“图片元数据读取”迁移到 Supabase + R2，并满足：按行懒加载 + blurhash 占位 + public 直链 + private 通过代理。

### Deliverables
- Supabase 数据源的 runs/run/grid/row API（保持 `/api/comfyui/*` 域名空间）。
- VirtualGrid：不再依赖 `local_image_path`，改为按行请求 row 元数据并渲染 thumb；Dialog 预览使用 display 变体；支持每 cell 多 batch（轮播/切换）。
- Blurhash 占位：client-only 解码（不 SSR inlining）。
- Private 图片代理端点：只代理 `display_*`/`thumb_*`；禁止 `original_png`；当前不鉴权直通（未来替换为 Supabase session 鉴权）。
- 文档：`documents/` 下说明实现方式 + Cloudflare（OpenNext）部署与本地开发。

### Definition of Done (verifiable)
- `pnpm lint` 通过。
- `pnpm build` 通过。
- `pnpm test:e2e` 通过（至少包含 runs → run detail → grid → 滚动触发行加载 → 图片可见 的回归）。
- 网格页面首屏不请求所有图片元数据：只在可视行触发 `/api/comfyui/run/:runDir/row?y_index=...`。
- blurhash 不在 SSR HTML 中出现（验证：查看 `view-source:` 不包含 blurhash 字符串；或 Playwright 断言 `page.content()` 不包含 blurhash 前缀）。

### Must Have
- 只用 `thumb_(avif|webp)` 展示网格 cell；Dialog 用 `display_(avif|webp)`。
- public 变体用直链 URL；private 变体用代理 URL。
- 不暴露 `original_png`（UI/API/代理均禁止）。
- 保留未来登录：private 代理与 Supabase 查询逻辑保持“单点可替换”，未来接入 Supabase session 时不需要重写整个数据流。

### Must NOT Have (guardrails)
- 不使用 Next `middleware.ts` 作为图片代理（Next 16 已更名 `proxy.ts`，且官方建议尽量避免；这里用 Route Handler）。
- 不在客户端打包/暴露 `SUPABASE_SERVICE_ROLE_KEY` 或 R2 私钥。
- 不读写 `.env`；只更新 `.env.example`。
- 不修改 Python uploader / Supabase migration（除非发现契约缺口且明确记录）。

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.
- Test decision: tests-after（新增/更新 Playwright E2E；必要时补少量 Node 侧契约断言）。
- QA policy: 每个任务都给出可执行验证（curl/Playwright/构建命令）并落证据到 `.sisyphus/evidence/`。

## Execution Strategy
### Parallel Execution Waves
Wave 1（基础契约/依赖/服务端）
- Supabase + R2 URL 构建基础、env/example、API 契约（runs/run/grid/row）。

Wave 2（前端网格/占位/按行懒加载）
- VirtualGrid 与 run detail 页面改造；blurhash 解码组件；多 batch 预览。

Wave 3（private 代理 + E2E + 文档 + 清理）
- private 代理端点（无鉴权直通）；E2E 用例补齐；`documents/` 文档；移除/降级旧本地图片路径依赖。

### Dependency Matrix (full)
- T1–T4 → T5–T8 → T9–T12 → T13–T16

## 新增依赖（必须用 pnpm add 安装）
- `@supabase/supabase-js`：在 Next Route Handlers 中查询 Supabase（本阶段只用 service role，避免引入“用户鉴权”）。
- `fast-blurhash`：客户端 blurhash 解码（轻量）。
- `aws4fetch`：private 代理端点在 Worker/Edge 运行时用 S3 兼容 API 签名访问 R2（避免依赖 Node fs/SDK）。

## TODOs

- [ ] 1. 定义 Web 侧 R2 URL 构建（不做鉴权，仅做变体/路径约束）

  **What to do**:
  - 新建 `lib/r2-url.ts`：
    - `publicObjectUrl(r2_key)`：使用 `R2_PUBLIC_BASE_URL` 拼接公开直链。
    - `privateObjectUrl(r2_key)`：返回站内代理 URL（例如 `/api/r2/private/<r2_key>`），按“分段 encode”而不是整串 encode。
    - 只允许 `display_*`/`thumb_*` 变体进入 URL 构建；明确拒绝 `original_png`。
    - 额外约束：仅接受以 `runs/` 开头的 key，避免被滥用为通用代理。

  **Must NOT do**:
  - 不引入 cookie/header 鉴权逻辑。
  - 不把任何 secret 通过 `NEXT_PUBLIC_*` 暴露。

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: 纯工具函数 + 约束。
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 3,4,7,12 | Blocked By: none

  **References**:
  - Next 约束: `https://nextjs.org/docs/messages/middleware-to-proxy`
  - R2 public/private 约定: `scripts/r2_upload/r2_provisioning.md`

  **Acceptance Criteria**:
  - [ ] 任意输入 `original_png` 或非 `runs/` 前缀会被拒绝（抛出受控错误）。

  **QA Scenarios**:
  ```
  Scenario: url builder rejects original_png
    Tool: Bash
    Steps: 调用对应 API（row / private proxy）触发 original_png
    Expected: 返回 400/404，且不泄露 r2 key 明文
    Evidence: .sisyphus/evidence/task-01-reject-original.txt
  ```

  **Commit**: YES | Message: `chore: 增加 R2 URL 构建与变体约束（无鉴权）` | Files: [`lib/r2-url.ts`]

- [ ] 2. 安装 Web 侧依赖（Supabase + blurhash + aws 签名）

  **What to do**:
  - 通过 `pnpm add` 安装：`@supabase/supabase-js fast-blurhash aws4fetch`。
  - 不手改 `package.json` 来添加依赖（必须由 pnpm 写入）。

  **Must NOT do**:
  - 不新增其它依赖（除非本计划后续任务明确需要）。

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: 单点依赖安装。
  - Skills: []

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 3,4,9,11 | Blocked By: none

  **Acceptance Criteria**:
  - [ ] `pnpm lint` 可运行（不要求 0 警告，但必须不因缺包崩溃）。

  **QA Scenarios**:
  ```
  Scenario: dependencies installed and importable
    Tool: Bash
    Steps: pnpm lint
    Expected: eslint 正常启动，不报 module not found
    Evidence: .sisyphus/evidence/task-02-pnpm-lint.txt
  ```

  **Commit**: YES | Message: `chore: 添加 Supabase/blurhash/R2 代理依赖` | Files: [`package.json`, `pnpm-lock.yaml`]

- [ ] 2.1 更新 `.env.example`（仅示例，不包含真实密钥）

  **What to do**:
  - 在 `.env.example` 中补充本阶段需要的键（全部留空或示例值）：
    - Supabase（服务器端读取）：`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
    - R2 public 直链：`R2_PUBLIC_BASE_URL`
    - R2 private 代理（S3 API 访问）：`R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_PRIVATE_BUCKET`
  - 明确注明：真实值写入本机 `.env` 或 Cloudflare secrets/vars；仓库内不提交。

  **Must NOT do**:
  - 不读写真实 `.env`。

  **Recommended Agent Profile**:
  - Category: `quick`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 3,4,5,6,7,12,13 | Blocked By: none

  **References**:
  - 现有示例 env: `.env.example`
  - 现有 Supabase/R2 变量说明: `scripts/r2_upload/supabase_workflow.md`, `scripts/r2_upload/r2_provisioning.md`

  **Acceptance Criteria**:
  - [ ] `.env.example` 不包含任何真实 key/token（只能是占位）。

  **Commit**: YES | Message: `docs(env): 补充网站侧 Supabase/R2 示例变量（无鉴权模式）` | Files: [`.env.example`]

- [ ] 3. 新建 Supabase server client（本阶段仅 service role）

  **What to do**:
  - 新建 `lib/supabase-server.ts`：
    - `createSupabaseServiceClient()`：读取 `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`（仅在服务器端 route handlers 使用）。
    - 严格：错误信息不得包含 key；只输出“是否配置/长度”。
  - 新建 `lib/supabase-types.ts`（最小手写类型，避免依赖自动生成）：runs/images/image_variants 的字段子集。

  **Must NOT do**:
  - 不把 service role client 暴露给 client components。

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: 需要正确处理 env、安全错误与类型。
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 4,5,6,7 | Blocked By: 2

  **References**:
  - DB schema: `supabase/migrations/20260220165906_init_r2_schema_rls.sql`
  - Python 侧字段（参考 blurhash/variants）：`scripts/r2_upload/supabase_writer.py`

  **Acceptance Criteria**:
  - [ ] 不配置 Supabase env 时，模块被 import 不崩溃（真正查询时再报配置错误）。

  **QA Scenarios**:
  ```
  Scenario: missing env yields controlled error
    Tool: Bash
    Steps: 不设置 Supabase env 启动 dev；请求 /api/comfyui/runs
    Expected: 返回 500 + 固定短文案（不包含 URL/key）
    Evidence: .sisyphus/evidence/task-03-missing-env.json
  ```

  **Commit**: YES | Message: `feat: 增加 Supabase server client（service role）` | Files: [`lib/supabase-server.ts`, `lib/supabase-types.ts`]

- [ ] 4. 将 `/api/comfyui/runs` 切换为 Supabase 数据源（保持返回 shape）

  **What to do**:
  - 更新 `app/api/comfyui/runs/route.ts`：
    - 统一使用 service client（当前不做用户鉴权；后续接入登录时再切回 anon+RLS）。
    - 查询 `runs` 表：select `run_dir, created_at, run_json`，按 created_at desc。
    - 从 `run_json.selection` 计算 `x_count/y_count/total_cells`；缺失时回退为 0。
    - 响应字段继续满足 `app/page.tsx` 现有 type guard（`run_dir/created_at/x_count/y_count/total_cells`）。

  **Must NOT do**:
  - 不从本地 `comfyui_api_outputs/` 读取。

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: 牵涉到现有页面契约稳定。
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 5,12 | Blocked By: 1,3

  **References**:
  - 现有 route: `app/api/comfyui/runs/route.ts`
  - 现有首页消费: `app/page.tsx`
  - runDir 正则: `lib/comfyui-types.ts`

  **Acceptance Criteria**:
  - [ ] 本地 `pnpm dev` 下首页 runs 列表可加载（有数据时显示；无数据时显示 empty，但不崩溃）。

  **QA Scenarios**:
  ```
  Scenario: runs endpoint returns expected shape
    Tool: Bash
    Steps: curl http://127.0.0.1:3000/api/comfyui/runs
    Expected: JSON 数组；每项包含 run_dir/created_at/x_count/y_count/total_cells
    Evidence: .sisyphus/evidence/task-04-runs.json
  ```

  **Commit**: YES | Message: `feat(api): runs 列表改为读取 Supabase` | Files: [`app/api/comfyui/runs/route.ts`]

- [ ] 5. 将 `/api/comfyui/run/[runDir]` 切换为 Supabase（提供 run 基本信息 + xColumns/yIndexes）

  **What to do**:
  - 更新 `app/api/comfyui/run/[runDir]/route.ts`：
    - 校验 runDir：复用 `lib/comfyui-types.ts:isValidRunDir`（不通过直接 404），并保持“短错误 + 不泄露路径/stack”的安全约束。
    - 用 Supabase 查询 `runs`：按 `run_dir` 精确匹配。
    - 组装响应：
      - `run`: `{ run_id, created_at, run_dir, selection: { total_cells } }`（run_id 从 run_json.run_id）。
      - `xLabels`: 使用 `run_json.selection.x_columns[]` 的 `description.zh`（fallback `X{index}`）。
      - `yLabels`: 仅返回占位（`Y{y_index}`），不拉 y_value。
    - 同时把 `x_columns` 与 `y_indexes`（原始数组）包含在响应（新增字段），供前端按需加载使用。

  **Must NOT do**:
  - 不再依赖 `discoverRunDirs()` allowlist（Supabase 本身是数据源）。

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 6,9,12 | Blocked By: 3

  **References**:
  - 当前 run route: `app/api/comfyui/run/[runDir]/route.ts`
  - run.json 结构（构造来源）: `scripts/generation/runner_payload.py`

  **Acceptance Criteria**:
  - [ ] `curl /api/comfyui/run/<runDir>` 返回 200 且包含 xLabels/yLabels（数组）。

  **QA Scenarios**:
  ```
  Scenario: invalid runDir returns 404 without leaking internals
    Tool: Bash
    Steps: curl -i http://127.0.0.1:3000/api/comfyui/run/../../etc/passwd
    Expected: 404；响应体不包含 /home/、C:\、stack、Traceback
    Evidence: .sisyphus/evidence/task-05-run-notfound.txt
  ```

  **Commit**: YES | Message: `feat(api): run 详情改为读取 Supabase 并暴露 x_columns/y_indexes` | Files: [`app/api/comfyui/run/[runDir]/route.ts`]

- [ ] 6. 将 `/api/comfyui/run/[runDir]/grid` 改为“轻量网格结构”（不返回图片元数据）

  **What to do**:
  - 更新 `app/api/comfyui/run/[runDir]/grid/route.ts`：
    - 先校验 runDir：复用 `lib/comfyui-types.ts:isValidRunDir`。
    - 查询 run 的 `run_json.selection`，返回：`x_columns`（含 type + description）与 `y_indexes`。
    - 不再返回 `cells`（或返回空对象），避免首次加载拉全量图片元数据。
    - 返回值需要包含 `x_count/y_count` 供 VirtualGrid 虚拟化。

  **Must NOT do**:
  - 不在该接口中返回任何图片 URL / blurhash。

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 9 | Blocked By: 5

  **Acceptance Criteria**:
  - [ ] grid 接口响应体不含 `blurhash`/`r2_key`/`http` 字符串。

  **QA Scenarios**:
  ```
  Scenario: grid endpoint is structure-only
    Tool: Bash
    Steps: curl http://127.0.0.1:3000/api/comfyui/run/<runDir>/grid
    Expected: 包含 x_columns/y_indexes；不包含 blurhash/r2_key
    Evidence: .sisyphus/evidence/task-06-grid-structure.json
  ```

  **Commit**: YES | Message: `feat(api): grid 改为仅返回结构（按需元数据由 row 接口提供）` | Files: [`app/api/comfyui/run/[runDir]/grid/route.ts`]

- [ ] 7. 新增按行元数据接口：`/api/comfyui/run/[runDir]/row?y_index=...`

  **What to do**:
  - 新建 `app/api/comfyui/run/[runDir]/row/route.ts`：
    - 先校验 runDir：复用 `lib/comfyui-types.ts:isValidRunDir`。
    - 输入：`runDir` + query `y_index`（整数）。
    - 查询 images + 嵌套 image_variants（一次请求完成）：
      - images 过滤：run_id（由 runs 表查到）+ y_index。
      - select 字段最小化：`x_index,y_index,batch_index,category,width,height,blurhash,metadata,image_variants(variant,bucket,r2_key,content_type,width,height)`。
    - 组装输出（强约束）：
      - 每个 cell 按 `x_index` 聚合为数组 items（按 batch_index 升序）。
      - 每个 item 只包含 thumb/display 的 avif/webp URL（用 `lib/r2-url.ts`），且 URL 生成规则：
        - `bucket='public'` → `publicObjectUrl(r2_key)`
        - `bucket='private'` → `privateObjectUrl(r2_key)`
      - 禁止输出 original_png。
      - 提取 meta：seed/prompt_hash/positive_prompt/y_value（来自 metadata JSON，可为空）。

  **Must NOT do**:
  - 不返回原始 `r2_key`（除非你明确决定需要；默认返回已拼好的 URL，避免前端持有 base url 逻辑）。

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 9 | Blocked By: 1,3,6

  **Acceptance Criteria**:
  - [ ] row 接口返回的 JSON 中不出现 `original_png`。
  - [ ] row 接口返回中不包含 `r2_key` 原文（只返回拼好的 URL）。

  **QA Scenarios**:
  ```
  Scenario: row endpoint returns urls + blurhash for one y_index
    Tool: Bash
    Steps: curl "http://127.0.0.1:3000/api/comfyui/run/<runDir>/row?y_index=0"
    Expected: cells 中每个 item 含 blurhash + thumb/display urls（至少 webp 或 avif 其一）
    Evidence: .sisyphus/evidence/task-07-row.json

  Scenario: original_png never exposed
    Tool: Bash
    Steps: curl row endpoint | grep original_png
    Expected: 无匹配
    Evidence: .sisyphus/evidence/task-07-no-original.txt
  ```

  **Commit**: YES | Message: `feat(api): 新增按行元数据接口（thumb/display + blurhash）` | Files: [`app/api/comfyui/run/[runDir]/row/route.ts`]

- [ ] 8. 更新首页 runs 列表 UI 以兼容 Supabase 数据与潜在空数据

  **What to do**:
  - 若 `/api/comfyui/runs` 返回空数组：保持 `app/page.tsx` 的 Empty 状态；不再提示“暂无 run.json”（改为更通用的“暂无可用 runs/或数据源未配置”）。

  **Recommended Agent Profile**:
  - Category: `quick`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: none | Blocked By: 4

  **Acceptance Criteria**:
  - [ ] 没有 Supabase 数据时首页不崩溃，空态文案合理。

  **Commit**: YES | Message: `chore(ui): runs 空态文案适配 Supabase 数据源` | Files: [`app/page.tsx`]

- [ ] 9. 重构 VirtualGrid：按行懒加载元数据 + 使用 R2 URL（替代 local_image_path）

  **What to do**:
  - 改造 `components/comfyui/virtual-grid.tsx`：
    - 输入 props 从 `grid: RunGridData` 调整为（建议）`grid: { x_columns, y_indexes }` + `runDir`。
    - 在虚拟行渲染时：
      - 依据可视行 index → 真实 `y_index = y_indexes[rowIndex]`。
      - 触发 fetch `/api/comfyui/run/${runDir}/row?y_index=${y_index}`（按单行）。
      - 建立 row cache（Map y_index → rowPayload），避免重复请求；并在卸载时 abort。
    - cell 渲染：
      - thumb 渲染用 `<picture>`：优先 avif，fallback webp。
      - 不再使用 `next/image`（避免 remotePatterns 与优化链；我们已提供 avif/webp 变体）。
      - Dialog 预览使用 display 变体；保持多张（batch）可切换。
    - 左侧 yLabel：先显示 `Y{y_index}`，row 数据到达后显示 y_value（若存在）。
    - seed 等 meta：从 row 数据提取，保持现有展示能力（至少 seed）。

  **Must NOT do**:
  - 不移除虚拟化（`@tanstack/react-virtual` 必须保留）。

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: 组件结构与数据流改动大，需谨慎避免性能回退。
  - Skills: []

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 12 | Blocked By: 6,7

  **References**:
  - 当前 VirtualGrid: `components/comfyui/virtual-grid.tsx`
  - 懒加载数据来源: `app/api/comfyui/run/[runDir]/row/route.ts`

  **Acceptance Criteria**:
  - [ ] Grid 首屏仅请求少量 row 接口（可视行 + overscan），滚动时才继续请求。
  - [ ] 页面网络请求中不再出现 `/api/comfyui/image/`。

  **QA Scenarios**:
  ```
  Scenario: scroll triggers row fetch
    Tool: Playwright
    Steps: 打开 /runs/<runDir>；监听网络请求；滚动 3 屏
    Expected: 只出现 row?y_index=... 的增量请求；请求数量随滚动增长
    Evidence: .sisyphus/evidence/task-09-row-fetch.log

  Scenario: no legacy local image route
    Tool: Playwright
    Steps: 打开 /runs/<runDir>；收集所有 <img> src
    Expected: src 不包含 /api/comfyui/image/
    Evidence: .sisyphus/evidence/task-09-img-src.json
  ```

  **Commit**: YES | Message: `feat(ui): VirtualGrid 改为按行懒加载并渲染 R2 缩略图` | Files: [`components/comfyui/virtual-grid.tsx`]

- [ ] 10. 实现 blurhash 占位（client-only 解码；不 SSR inlining）

  **What to do**:
  - 新建 `components/comfyui/blurhash-canvas.tsx`：
    - 仅 client 组件；用 `fast-blurhash` 解码到 32x32（或 24x24），绘制到 canvas。
    - 用 CSS 放大 + blur 作为占位。
  - 在 VirtualGrid cell 中：
    - `<img>` 未加载完成前显示 blurhash canvas；onLoad 后淡出。
  - 确保 blurhash 字符串仅来自 row JSON（由客户端 fetch），不在 SSR HTML 中出现。

  **Recommended Agent Profile**:
  - Category: `visual-engineering` — Reason: 占位渲染与过渡需要视觉验证。
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 12 | Blocked By: 9

  **Acceptance Criteria**:
  - [ ] Playwright 可断言：图片加载前存在 blurhash placeholder，加载后主图可见。

  **QA Scenarios**:
  ```
  Scenario: placeholder appears before image load
    Tool: Playwright
    Steps: network throttling；打开 /runs/<runDir>
    Expected: placeholder 可见；随后主图 opacity 过渡到 1
    Evidence: .sisyphus/evidence/task-10-placeholder.png
  ```

  **Commit**: YES | Message: `feat(ui): 增加 blurhash 占位组件并接入网格` | Files: [`components/comfyui/blurhash-canvas.tsx`, `components/comfyui/virtual-grid.tsx`]

- [ ] 11. 更新 run detail 页面：使用新 grid/row 数据模型

  **What to do**:
  - 更新 `app/runs/[runDir]/page.tsx`：
    - 仍并行 fetch run detail + grid structure。
    - type guards 更新：grid 不再有 cells。
    - 传给 VirtualGrid 的 props 更新。

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 12 | Blocked By: 5,6,9

  **Acceptance Criteria**:
  - [ ] `/runs/<runDir>` 页面能渲染出 grid 且滚动不报错。

  **Commit**: YES | Message: `feat(page): run 详情页适配按行懒加载网格` | Files: [`app/runs/[runDir]/page.tsx`]

- [ ] 12. 实现 private 图片代理端点（R2 S3 API + aws4fetch；无鉴权直通）

  **What to do**:
  - 新建 `app/api/r2/private/[...r2Key]/route.ts`：
    - 读取路径参数拼回 `r2_key`（注意 decode/segment join）。
    - 强校验：只允许 key 前缀 `runs/`，且文件名必须是 `display_*.{avif|webp}` 或 `thumb_*.{avif|webp}`；拒绝 `.png` 与 `original_png`。
    - 不做鉴权：任何请求只要 key 满足约束就允许代理（未来接入登录时再加鉴权）。
    - 使用 `aws4fetch` 对 `R2_ENDPOINT` 发起签名 GET，路径采用 `/${R2_PRIVATE_BUCKET}/${r2_key}`。
    - 透传 content-type，并设置 `Cache-Control: private, max-age=0, no-cache`（或使用 R2 元数据）。
    - 错误响应不得泄露 endpoint/bucket/key 明文（可用 key hash12）。

  **Must NOT do**:
  - 不使用 Next middleware/proxy 文件。

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: 涉及安全校验 + 代理流式响应。
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: none | Blocked By: 1,2

  **References**:
  - R2 官方 Workers/S3 思路: `scripts/r2_upload/r2_provisioning.md`
  - External docs: `https://developers.cloudflare.com/r2/api/s3/`

  **Acceptance Criteria**:
  - [ ] 对非法 key（非 `runs/` 前缀、`.png`、`original_png`）返回 400/404（短文案），且不会向 R2 发起请求。
  - [ ] 对合法 key：在配置了 R2 私有桶访问凭据且对象存在时，返回 200 并能被浏览器 `<img>` 正常渲染。
  - [ ] 任意错误响应不包含 endpoint/bucket/key 明文（允许 key hash12）。

  **QA Scenarios**:
  ```
  Scenario: blocks original png
    Tool: Bash
    Steps: curl -i http://127.0.0.1:3000/api/r2/private/runs/.../original_png.png
    Expected: 404 或 400（固定短文案），且不尝试访问 R2
    Evidence: .sisyphus/evidence/task-12-block-original.txt

  Scenario: proxies private display/thumb when object exists
    Tool: Bash
    Steps: curl -I http://127.0.0.1:3000/api/r2/private/<somePrivateDisplayOrThumbKey>
    Expected: 200 + Content-Type: image/(avif|webp)
    Evidence: .sisyphus/evidence/task-12-private-proxy-head.txt
  ```

  **Commit**: YES | Message: `feat(api): private R2 图片代理端点（无鉴权直通）` | Files: [`app/api/r2/private/[...r2Key]/route.ts`]

- [ ] 13. Playwright E2E：补齐 runs → detail → grid → 滚动懒加载 → 图片可见

  **What to do**:
  - 新增/补齐 `e2e/task-14-main-flow.spec.ts`（按 `e2e/AGENTS.md` 指引）：
    - 进入首页，点击某个 run。
    - 断言 grid 可见，且滚动后 row 请求增长。
    - 断言至少一个 cell 图片可见（normal 列）。
  - 新增 `e2e/task-17-r2-src.spec.ts`：
    - 断言图片 src 不包含 `/api/comfyui/image/`。
    - normal 列 src 为 `https://...`（public base url），或符合预期域名。
  - private 代理链路验证（可条件执行）：
    - 若 row 接口返回的任意 `thumb/display` URL 以 `/api/r2/private/` 开头，则断言该图片可成功加载；否则该用例 `test.skip()`（避免在没有 private display/thumb 数据时误报）。
  - 运行门禁：若未配置 `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`，则这些“数据相关”用例应 `test.skip()`（保留 `e2e/smoke.spec.ts` 作为最低保障），避免在未配置环境下红灯。

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
  - Skills: [`playwright`] — Reason: 端到端验证网络行为与占位逻辑。

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 14 | Blocked By: 9,11

  **Acceptance Criteria**:
  - [ ] `pnpm test:e2e` 通过（未配置 Supabase 时允许相关用例 skip，但 smoke 必须通过）。

  **QA Scenarios**:
  ```
  Scenario: main flow works
    Tool: Playwright
    Steps: pnpm test:e2e -- -g "main flow"
    Expected: tests pass; evidence output in .sisyphus/evidence/playwright/
    Evidence: .sisyphus/evidence/playwright/
  ```

  **Commit**: YES | Message: `test(e2e): 增加 R2+按行懒加载主流程回归` | Files: [`e2e/task-14-main-flow.spec.ts`, `e2e/task-17-r2-src.spec.ts`]

- [ ] 14. ESLint/TypeScript 回归：修复类型守卫与边界错误

  **What to do**:
  - 跟进新 API payload 的 type guards（`app/runs/[runDir]/page.tsx`）。
  - 确保 strict 下不引入 any 泄漏。

  **Recommended Agent Profile**:
  - Category: `quick`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 15 | Blocked By: 13

  **Acceptance Criteria**:
  - [ ] `pnpm lint` 通过。

  **Commit**: YES | Message: `chore: 修复迁移后的类型与 lint 问题` | Files: ["(按实际修改列出)"]

- [ ] 15. 文档：实现说明 + Cloudflare Workers 部署 + 本地开发

  **What to do**:
  - 新建 `documents/r2-supabase-workers.md`：
    - 架构图（文字即可）：Supabase（runs/images/image_variants）→ Next API → VirtualGrid；public 直链；private 代理。
    - 环境变量清单（只引用 `.env.example` 键名，不写真实值）。
    - 本地开发：
      - `pnpm dev`（网站）；
      - Supabase 本地/远程两种方式（引用 `scripts/r2_upload/supabase_workflow.md`）。
      - 如何验证 private 代理：提供一个用 curl 验证 `/api/r2/private/...` 返回 200 的示例（不包含真实 key）。
    - 部署到 Cloudflare：
      - 推荐 `@opennextjs/cloudflare`（OpenNext）路线；
      - 需要的 wrangler 配置点（`nodejs_compat`、secrets）；
      - public bucket 自定义域名建议；private 代理的安全注意。
    - Next “middleware→proxy” 说明：我们不用它做图片代理。

  **Recommended Agent Profile**:
  - Category: `writing`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 16 | Blocked By: 12

  **Acceptance Criteria**:
  - [ ] 文档包含：实现方式、部署步骤、本地开发步骤、private 代理验证方式、未来接入登录的替换点。

  **Commit**: YES | Message: `docs: 增加 R2+Supabase 迁移与 Cloudflare 部署说明` | Files: [`documents/r2-supabase-workers.md`]

- [ ] 16. 最终回归波：build + e2e + 安全检查（不泄露敏感信息）

  **What to do**:
  - 运行：`pnpm build`、`pnpm test:e2e`。
  - 安全检查：
    - 任意 404/500 响应体不包含 `/home/`、`C:\\`、`SUPABASE_`、`R2_`、stack/Traceback。
    - private 代理拒绝 `.png` 与任何 `original_png`。

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
  - Skills: []

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: none | Blocked By: 14,15

  **Acceptance Criteria**:
  - [ ] `pnpm build` 通过。
  - [ ] `pnpm test:e2e` 通过。

  **Commit**: YES | Message: `chore: 完成 R2+Supabase 迁移最终回归` | Files: ["(按实际修改列出)"]

## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. Real Manual QA — unspecified-high (+ playwright)
- [ ] F4. Scope Fidelity Check — deep

## Commit Strategy
- 提交频率：完成每个可运行里程碑就提交（至少：依赖/基础库、API 切换、VirtualGrid 懒加载、private 代理、E2E、文档、最终回归）。
- Commit message：中文，格式保持简短明确（例如 `feat(api): ...`）。

## Success Criteria
- 访问 `/` 能看到 runs；访问 `/runs/[runDir]` 能看到虚拟网格；滚动时按行加载图片元数据；图片先 blurhash 占位后出现；public 走直链、private 走代理；无 `original_png` 暴露；E2E/Build/Lint 全部通过；`documents/` 有可操作的部署与开发说明。
