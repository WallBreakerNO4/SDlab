# 网页性能优化修改方案

<!-- Generated: 2026-05-13 | Updated: 2026-05-13（审查修正） -->

## 审查修正说明（2026-05-13）

原方案经源码逐项审查后做以下调整：

1. **`pnpm build` 修复提升为 P0 前置项**：当前 `initOpenNextCloudflareForDev()` 在 `next.config.ts` 顶层执行，导致 `pnpm build` 触发 Wrangler remote proxy 返回 401 而失败。这是真实 bug，非纯优化，需在缓存优化之前修复。
2. **高风险项拆分**：以下子方案因改动范围过大或涉及安全架构变更，已移至 `DEFERRED_HIGH_RISK_ITEMS.md`：
   - grant 从 query string 迁移到 header/cookie（原 P0-2.5）：需独立安全审查
   - row chunk JSON 产物格式变更（原 P0-2.6）：涉及上传管线 + 前端解析，架构级改动
   - 首页 HorizontalScrollList DOM 重构（原 P1-6）：Safari 回归风险高，需独立 E2E 专项
3. **P1-4 的 `force-cache` 建议采纳**：`release_id` 由 manifest 内容 SHA256 派生（`manifest.py`），资源不可变，使用 `force-cache` 安全。
4. **P0-2 的 ETag/If-None-Match 实现细节补充**：当前 `app/api/private-object/route.ts` 已设置 `ETag`（line 70），但未检查请求的 `If-None-Match` header，需补充条件返回逻辑。
5. **实现顺序从 3 阶段调整为 4 阶段**：前置修复 → 基础缓存 → 交互优化 → 结构与观测。

## 目标与依据

本方案基于当前仓库源码、近期 Git 提交记录，以及 Cloudflare Workers Observability MCP 中 `sd-style-lab` 的线上请求样本整理。目标是在尽量保留现有用户体验和访问控制语义的前提下，降低首页首屏等待、详情页滚动加载延迟、登录态接口开销和客户端渲染成本。

近期提交判断：

- `60d59ba`（2026-04-28）：最后一次明确修改首页前端行为，修复 Safari 卡片布局与 hover 跳位。
- `d22466e`（2026-05-02）：依赖升级。
- `24d6a86`、`2fd1c7e`（2026-05-03）：模型配置与 Python/R2 删除脚本相关，前端代码路径未变。

Cloudflare 线上样本判断：

- `GET /` 完整 HTML 请求多次出现约 `1.5s` 到 `3.1s` wall time，CPU 样本可到 `250ms` 到 `560ms`。
- `GET /api/private-object` 行 JSON 请求常见 `200ms` 到 `800ms` wall time，样本中出现 `1199ms`、`1318ms`、`1494ms`，CPU 通常只有个位数到十几毫秒。
- `GET /api/viewer/style-prompt-favorites` 样本出现 `304ms`、`891ms`、`1008ms`、`1513ms`，还有 canceled 请求约 `1678ms`。
- MCP 当前暴露的是 Workers Observability，可看 Worker 真实请求与服务端耗时；浏览器端 Core Web Vitals 需要补充 Cloudflare Web Analytics 或自定义 RUM 上报。

仓库内访问语义判断：

- 图片 category 有三种：`normal`、`advance`、`nsfw`，定义见 `lib/supabase-types.ts` 与 `scripts/r2_upload/upload_contracts.py`。
- R2 bucket 映射为 `normal -> public`，`advance/nsfw -> private`，测试见 `tests/test_r2_keys.py`。
- view manifest 生成三套 row：`public` 只含 `normal`，`auth_sfw` 含 `normal + advance`，`auth_nsfw` 含 `normal + advance + nsfw`，逻辑见 `scripts/r2_upload/manifest.py`。
- 因此登录用户关闭 NSFW 时仍需要 `auth_sfw`，不能直接退回 `public` 行 JSON，否则会丢失 Advance 图片。

## 优先级总览

| 优先级 | 修改项 | 主要收益 | 行为变更风险 |
| --- | --- | --- | --- |
| P0 | 构建配置修正（前置）| 恢复本地 `pnpm build`，可观测 bundle 体积 | 无 |
| P0 | 首页 runs 列表服务端缓存 | 降低 `GET /` TTFB、Supabase 查询和 Worker CPU | 低 |
| P0 | bootstrap 加载并行化与缓存策略 | 缩短详情页进入可交互网格的时间 | 低 |
| P0 | 私有行 JSON 条件请求与分级缓存 | 降低 `/api/private-object` 慢请求，保留 Advance | 中 |
| P0 | 详情页行请求并发控制 | 降低滚动时请求尖峰和 R2/Worker 排队 | 中 |
| P1 | 收藏列表延后加载 | 降低登录用户进入详情页时的附加等待 | 中 |
| P2 | Root layout 认证读取瘦身 | 降低所有页面 SSR 固定开销 | 中 |
| P2 | 清理未使用组件与依赖 | 降低潜在 bundle 风险 | 低 |
| P2 | 增加 RUM 性能观测 | 让后续优化有浏览器端真实指标 | 低 |

> **已拆分的高风险项**（见 `DEFERRED_HIGH_RISK_ITEMS.md`）：
> - grant 从 query string 迁移到 header/cookie（安全架构变更）
> - row chunk JSON 产物格式变更（上传 + 前端同步改）
> - 首页 HorizontalScrollList DOM 收敛与 blurhash 降级（Safari 回归风险）

## 0. 构建配置修正（前置）

### 现状

相关代码：

- `next.config.ts`

`initOpenNextCloudflareForDev()` 在配置文件顶层执行（`next.config.ts:8`）。本地运行 `pnpm build` 时会触发 Wrangler remote proxy，当前环境返回 401，导致无法获取 Next build 输出和 bundle 体积数据。此为**真实 bug**，非纯优化。

### 怎么做

1. 仅在 `next dev` 场景初始化 OpenNext Cloudflare dev 绑定：
   - 通过判断 `process.argv` 是否包含 `"dev"` 或检查 `NODE_ENV` 相关环境变量。
   - 方案 A：检查 `process.argv` 中是否含 `"dev"` 子命令。
   - 方案 B：设置环境变量（如 `SKIP_OPENNEXT_DEV=1`），CI/build 脚本中设置该变量。
   - build 阶段跳过 `initOpenNextCloudflareForDev()`。

2. 保持本地 dev 的 Miniflare 绑定能力：
   - `pnpm dev` 仍初始化。
   - `pnpm build` 只做构建。

3. 增加一条 CI/本地说明：
   - 如果需要远程 Wrangler，会要求登录。
   - 普通 build 不应依赖 Wrangler remote session。

### 预期改善

- 恢复本地 `pnpm build`。
- 能查看 Next route size、First Load JS 等输出。
- 后续 bundle 优化有基线数据。

### 影响

- 需要确认 `pnpm dev` 仍能拿到 R2/KV binding。
- 只影响开发和构建流程。

### 行为变更

无线上行为变更。

### 验证

- `pnpm build` 应成功。
- `pnpm dev` 下依赖 Cloudflare binding 的 route 仍可运行。

---

## 1. 首页 runs 列表服务端缓存

### 现状

相关代码：

- `app/page.tsx`
- `lib/run-list.ts`
- `app/api/comfyui/runs/route.ts`

首页服务端渲染时会调用 `listRunSummaries()`（`lib/run-list.ts:114-174`），该函数每次创建 Supabase client，并查询 `run_list_items` 视图中包含封面图、主页缩略图、模型描述等字段的列表。Cloudflare 样本显示 `GET /` 完整 HTML 请求 wall time 偏高，和该链路的 Supabase 查询、JSON 组装、React SSR 成本相符。

### 怎么做

1. 给 `listRunSummaries()` 外层增加缓存函数：
   - 使用 `unstable_cache()` 包装 Supabase 查询。
   - cache key 使用固定 `["run-list-summaries"]`。
   - 初始 TTL 建议 `300s` 到 `900s`。
   - tags 使用 `["run-list"]`，为后续上传脚本触发 revalidate 留入口。
   - **注意**：`unstable_cache()` 必须在 Server Component 或 Route Handler 的请求上下文中调用（即从 `app/page.tsx` 或 `app/api/comfyui/runs/route.ts` 中调用）。建议在 `lib/run-list.ts` 中同时导出缓存版和未缓存版：

     ```ts
     // lib/run-list.ts
     import { unstable_cache } from "next/cache";

     export async function loadRunSummariesUncached(): Promise<RunSummary[]> {
       // ... 当前 listRunSummaries 的完整实现
     }

     export const listRunSummaries = unstable_cache(
       loadRunSummariesUncached,
       ["run-list-summaries"],
       { revalidate: 300, tags: ["run-list"] },
     );
     ```

2. 如果上传链路未来能通知 Web，可增加轻量 revalidate route：
   - `POST /api/internal/revalidate`
   - 使用服务端密钥保护。
   - 上传新 run、删除 run、更新封面图后调用 `revalidateTag("run-list")`。

3. 若短期不加 revalidate route，直接采用短 TTL：
   - 目录更新最多延迟几分钟。
   - 实现成本低，适合第一阶段。

### 预期改善

- 明显降低 `GET /` 的 Supabase 往返次数。
- 降低 Worker CPU 和 wall time。
- 提升未登录用户首页 TTFB。
- 减少 Supabase 项目的热读压力。

### 影响

- 首页模型目录数据会出现短时间缓存。
- 删除 run 后，旧卡片可能在 TTL 内继续出现。
- 上传新模型后，首页展示可能延迟到缓存过期。

### 行为变更

有轻微行为变更：目录更新从实时读取变为短时缓存。用户浏览、点击模型页、图片预览行为保持一致。

### 验证

- 本地确认首页可正常加载。
- 用 Cloudflare Observability 对比上线前后 `GET /` wall time。
- 如果增加 revalidate route，需要测试新增 run、删除 run 后首页是否按预期刷新。

---

## 2. 详情页 bootstrap 加载并行化与缓存策略

### 现状

相关代码：

- `app/models/[runDir]/use-model-detail-data.ts`

当前加载顺序（`use-model-detail-data.ts:49-104`）：

1. 请求 `view/current.json`（`cache: "no-store"`，line 51-55）
2. 如果登录，请求 `/api/comfyui/run/[runDir]/access`（`cache: "no-store"`，line 72-90）
3. 根据结果请求 `bootstrap.sfw.json` 或 `bootstrap.nsfw.json`（`cache: "no-store"`，line 101-104）

其中 `current.json` 和 access 两步存在串行等待，但两者相互独立——`current.json` 返回 `release_id`，access 返回 `viewer_variant` + `grant`，不存在依赖关系。

当前所有 fetch 均使用 `cache: "no-store"`，会削弱浏览器缓存收益。其中 `bootstrap.sfw.json` 指向不可变的 `release_id` 资源（由 manifest 内容 SHA256 派生），可以安全缓存。

### 怎么做

1. 并行启动 current 和 access：
   - `currentPromise` 立即发起。
   - 登录用户的 `accessPromise` 同时发起。
   - 等 current `release_id` 确定后再决定 bootstrap URL。

2. 调整各请求的缓存策略：
   - `current.json`：保持 `no-store` 或短 TTL（该文件在上传新 release 后会更新）。
   - `bootstrap.sfw.json`：指向 `release_id` 的资源不可变，改为 `cache: "force-cache"`。
   - 登录 SFW 仍用公开 `bootstrap.sfw.json` 做基础索引，再通过私有 `auth_sfw` row JSON 补齐 Advance（当前架构已支持此模式，bootstrap_sfw 中 `accessible_categories={"normal"}`，行级别 row JSON 才包含 Advance 图片数据）。
   - 私有 NSFW bootstrap 仍保持 `no-store` 或短私有缓存。

3. （可选）将 `current.json` 的职责收窄：
   - 如果 `release_id` 已嵌入页面 props 或首页链接数据，详情页可减少一次请求。
   - 这需要首页数据携带 current `release_id`，改动略大，列为远期优化。

### 预期改善

- 登录用户详情页少一次串行等待（约 1 个 RTT）。
- 公开 bootstrap 重复进入更快（命中浏览器缓存）。
- 登录 SFW 保留 Advance，同时减少基础索引重复拉取。

### 影响

- 需要确认 `release_id` 资源不可变（已确认：`manifest.py` 中 release 由内容 SHA256 前 20 位派生）。
- 如果 `current.json` 更新频繁，缓存 TTL 需要保持较短。

### 行为变更

基本无可见行为变更。

### 验证

- 打开详情页首屏，Network waterfall 应缩短（current 和 access 请求在时间轴上重叠）。
- 切换登录状态、NSFW 偏好时仍加载对应视图。
- 删除或更新 run 后，404/错误态仍正确。

---

## 3. 私有行 JSON 条件请求与分级缓存

### 现状

相关代码：

- `components/comfyui/use-virtual-grid-rows.ts`
- `app/api/private-object/route.ts`
- `scripts/r2_upload/manifest.py`
- `scripts/r2_upload/r2_keys.py`

当前 viewer variant 的含义是：

- `public`：匿名公开视图，只能看到 `normal`。
- `auth_sfw`：登录后关闭 NSFW，可看到 `normal + advance`。
- `auth_nsfw`：登录后开启 NSFW，可看到 `normal + advance + nsfw`。

`buildRowManifestUrl()`（`use-virtual-grid-rows.ts:21-40`）中只要存在 `viewAccess`，就会通过 `/api/private-object` 请求 `rows/auth_sfw/{y}.json` 或 `rows/auth_nsfw/{y}.json`。这条路径是必要的，因为 `advance` 的缩略图和展示图在 private bucket，登录 SFW 视图需要保留它们。

Cloudflare 样本显示 `/api/private-object` 行 JSON 请求延迟明显。CPU 很低但 wall time 高，说明主要成本来自代理路径、R2 读取、网络往返和请求数量。

**当前 route 已有 ETag 输出但无 If-None-Match 检查**：`app/api/private-object/route.ts:70` 设置了 `ETag: object.httpEtag`，但没有检查请求中的 `If-None-Match` header，导致客户端无法利用条件请求跳过重复下载。

### 怎么做

1. 保留三套 viewer variant 语义保持不变。

2. 给 `/api/private-object` 增加条件请求支持：
   - 检查请求 `If-None-Match` header。
   - 如果与 R2 object `httpEtag` 匹配，直接返回 `304 Not Modified`。
   - 保留当前已有的 `ETag`、`Content-Length`、`Cache-Control`。

   伪代码：
   ```ts
   const ifNoneMatch = request.headers.get("If-None-Match");
   if (ifNoneMatch && ifNoneMatch === object.httpEtag) {
     return new Response(null, { status: 304 });
   }
   ```

3. 按文件类型分级设置 `Cache-Control`：
   - row JSON（key 以 `.json` 结尾）：`private, max-age=300`（保留现有策略，配合 ETag）。
   - 图片变体（`display_*.webp/avif`、`thumb_*.webp/avif`）：`private, max-age=0, no-cache`（保持敏感内容即时校验）。

4. 改善前端 row cache 跨导航复用：
   - 当前 `rowCacheRef` 只在组件生命周期内有效（组件卸载即丢失）。
   - 增加模块级内存缓存（或 WeakMap），key 使用 `runDir + releaseId + viewerVariant + yIndex`。
   - 同一用户在详情页来回导航、切换弹窗、返回页面时复用已加载 row JSON。
   - grant 变化不应清空已解析的 row 数据；图片对象 URL 仍按现有私有缓存处理。

### 预期改善

- 重复访问相同 row JSON 时返回 304，节省带宽和解析成本。
- 页面导航间 row cache 复用，减少重复请求。
- 登录 SFW 仍保留 Advance 图片展示。

### 影响

- row JSON 和图片文件的缓存策略需要仔细区分。
- 模块级 row cache 需要考虑内存上限（当前单 run 的 row JSON 体积较小，风险可控）。

### 行为变更

无可见行为变更。登录 SFW 仍显示 `normal + advance`，登录 NSFW 仍显示三类图片，匿名用户仍只显示 `normal`。

### 验证

- 登录后关闭 NSFW，详情页 row JSON 应保持 `auth_sfw`，并能展示 Advance。
- 匿名访问详情页，row JSON 只能包含 `normal`。
- 登录后开启 NSFW，row JSON 应为 `auth_nsfw`，并包含三类图片。
- `tests/test_r2_manifest.py` 需要增加明确含 `advance` 的样本，验证 `auth_sfw` 包含 `normal + advance`。
- Cloudflare Observability 中 `/api/private-object` 的 304 返回比例应上升。

---

## 4. 详情页行请求并发控制

### 现状

相关代码：

- `components/comfyui/virtual-grid.tsx`
- `components/comfyui/use-virtual-grid-rows.ts`

虚拟网格会对可视行和 overscan 行调用 `requestRow()`（`use-virtual-grid-rows.ts:60-152`）。当前逻辑去重了同一行请求（line 63-64），但没有限制不同 yIndex 之间的并发数量。快速滚动或初次进入大网格时，会同时发出多条 row JSON 请求。

### 怎么做

1. 在 `useVirtualGridRows()` 中引入轻量请求队列：
   - `maxConcurrent` 初始建议 `4` 到 `6`。
   - 可视区域优先，远端 overscan 次之。
   - 已经离开可视范围且未开始的任务可从队列移除。
   - 实现方案建议：基于 Promise 的手动队列（不引入新依赖），核心逻辑为维护 `pending: Map<number, () => Promise<void>>` 和 `running: Set<number>`，在有 slot 空闲时取优先级最高的 pending 任务执行。

2. 调整虚拟化 overscan：
   - 当前 `overscan: 8`。
   - 可以按网络情况改成 `4` 到 `6`。
   - 或根据滚动速度动态调整（快速滚动时降低 overscan）。

3. 增加近邻预取：
   - 用户停稳后预取下一屏。
   - 快速滚动时降低预取，避免请求堆积。

### 预期改善

- 降低 R2 和 Worker 代理突发压力。
- 减少慢请求堆积导致的可视行等待。
- 快速滚动时页面更稳，网络面板更干净。

### 影响

- 首屏可能少预取几行，但可视行优先级更高。
- 请求队列实现会增加前端状态复杂度。

### 行为变更

轻微行为变更：快速滚动到很远位置时，远处预取会更克制；可视区域加载优先级提升。用户看到的内容和权限语义保持一致。

### 验证

- E2E 覆盖详情页初次加载、快速滚动、跳转指定行、搜索跳转。
- Network 中同一时间 row JSON 请求数应被限制。
- Cloudflare 中 `/api/private-object` 峰值请求密度应下降。

---

## 5. 收藏列表延后加载

### 现状

相关代码：

- `app/models/[runDir]/use-style-prompt-favorites.ts`
- `app/api/viewer/style-prompt-favorites/route.ts`
- `components/comfyui/virtual-grid.tsx`

登录用户进入模型详情页后，前端立即请求收藏列表。Cloudflare 样本显示该 API 偶发慢请求，并出现 canceled 请求。该功能对首屏网格可见内容并非必要。

### 怎么做

采用方案 A：延后加载。

- 在 `requestIdleCallback` 或短 `setTimeout`（如 500ms）后拉收藏。
- 首屏网格先渲染。
- 收藏按钮先显示普通状态，收藏数据回来后补齐高亮。
- 保留当前 hook 的 optimistic UI 机制（`pendingKeys`），收藏/取消收藏操作仍即时响应。

> 方案 B（按需加载：点击弹窗时才拉取）和方案 C（服务端缓存：用户维度数据不适合）暂不采用。

### 预期改善

- 降低登录用户详情页首屏请求数量（少 1 个 API 调用）。
- 减少慢收藏 API 对主体验的影响。
- 避免页面切换时产生 canceled 请求。

### 影响

- 收藏星标可能首屏后 0.5~2 秒才显示高亮。
- 极少数情况下用户可能在收藏数据未返回时就尝试收藏（当前 optimistic UI 机制可处理）。

### 行为变更

有轻微可见行为变更：收藏状态可能延迟 0.5~2 秒显示。核心收藏、取消收藏、跳转收藏行为保持一致。

### 验证

- 登录用户打开详情页时，首屏 Network 不再立即出现收藏 API，或在 `setTimeout` 后出现。
- 收藏入口打开后列表仍正确。
- 星标状态加载完成后与用户数据一致。

---

## 6. Root layout 认证读取瘦身

### 现状

相关代码：

- `app/layout.tsx`
- `components/auth-provider.tsx`
- `middleware.ts`

Root layout 每次 SSR 都尝试创建服务端 Supabase client 并调用 `auth.getUser()`（`app/layout.tsx:67-75`）。这会给所有页面增加固定服务端开销，包括 `/info`、`/privacy-policy` 等纯静态页也会执行。

Middleware（`middleware.ts:57-63`）已限定只匹配 auth callback、偏好接口、access route，没有覆盖所有页面。

### 怎么做

采用方案：仅在有 session cookie 时才 SSR 读取 user。

- 在 `app/layout.tsx` 中先检查 `cookieStore` 是否包含 Supabase session cookie（key 通常为包含 `sb-` 前缀的 cookie）。
- 若不存在 session cookie，直接设置 `initialUser = null`，跳过 `auth.getUser()` 调用。
- 若存在 session cookie，保持现有行为（调用 `auth.getUser()` 获取初始用户）。

```ts
// app/layout.tsx 改造要点
const cookieStore = await cookies();
let initialUser = null;

const hasSessionCookie = cookieStore.getAll()
  .some((c) => c.name.includes("sb-") && c.name.endsWith("-auth-token"));

if (hasSessionCookie) {
  try {
    const supabase = await createSupabaseAuthClient();
    const { data: { user } } = await supabase.auth.getUser();
    initialUser = user ?? null;
  } catch {
    initialUser = null;
  }
}
```

### 预期改善

- 匿名用户访问所有页面时免去 `auth.getUser()` 调用，降低 SSR CPU 和 wall time。
- 公共静态页（`/info`、`/privacy-policy`）接近纯静态输出。

### 影响

- Header 登录态对已有 session 的用户无变化（仍 SSR 获取）。
- 匿名用户体验无变化。
- 需要正确识别 Supabase session cookie 名称。

### 行为变更

无可见行为变更。只有当用户浏览器存在有效 session cookie 时才会 SSR 读取用户状态，这与现有行为一致。

### 验证

- 匿名访问首页、info、privacy，Cloudflare 中对应请求 CPU 应下降。
- 登录用户刷新页面，Header 仍显示正确用户状态。
- OAuth callback 后仍能回到正确页面（session cookie 会被正确设置）。

---

## 7. 清理未使用组件与依赖

### 现状

仓库依赖中包含 `recharts`、`embla-carousel-react`、`react-day-picker`、`react-resizable-panels`、`vaul` 等组件库。源码中部分只在 `components/ui/*` primitive 文件内出现，没有业务调用。

### 怎么做

1. 先跑静态引用检查：
   - 找出没有业务入口引用的 UI primitive。
   - 确认 `components/component-example.tsx` 是否仍需保留。

2. 对确实未使用的 primitive：
   - 第一阶段只记录，不删依赖。
   - 第二阶段再删除 UI 文件和依赖，避免误伤 shadcn 后续使用。

3. 对巨大图标库：
   - 检查 `@hugeicons/core-free-icons` 是否被 tree shaking。
   - 保持具名导入。
   - 避免从聚合入口一次性导入大量图标。

### 预期改善

- 降低潜在 bundle 风险。
- 减少安装体积和 lockfile churn。
- 构建分析更清晰。

### 影响

- 删除未使用组件可能影响未来开发便利性。
- 如果某些组件仅被动态引用，静态检查可能漏判。

### 行为变更

无用户可见行为变更，前提是只删除无业务引用的代码和依赖。

### 验证

- `pnpm build`
- `pnpm lint`
- E2E 覆盖当前页面。

---

## 8. 增加 RUM 性能观测

### 现状

Cloudflare MCP 当前能看到 Worker 请求、状态、CPU、wall time。浏览器侧 LCP、INP、CLS、图片加载、设备分布和地区分布仍缺少直接数据。

### 怎么做

1. 优先接入 Cloudflare Web Analytics：
   - 开启站点 Web Analytics。
   - 确认是否能在 Cloudflare 面板看到 Core Web Vitals。
   - 后续通过 Cloudflare API 或手动导出对比。

2. 同时考虑自定义 `useReportWebVitals`：
   - 新建客户端组件上报 Next Web Vitals。
   - 上报 endpoint 只收聚合必要字段：metric name、value、route、navigation type、device hints。
   - 避免上报用户身份、完整 URL query、grant、R2 key。

3. 最少监控指标：
   - 首页：LCP、CLS、INP、TTFB。
   - 详情页：grid ready 时间、首批 row ready 时间、row request count。
   - 私有代理：按路径类型统计 `/api/private-object` wall time。

### 预期改善

- 后续优化能用浏览器真实体验判断。
- 能区分服务端慢、图片慢、JS hydration 慢、交互慢。
- 方便观察 Safari 和移动端问题。

### 影响

- 增加少量前端脚本和上报请求。
- 需要隐私审查，避免采集敏感信息。

### 行为变更

无用户可见行为变更。网络面板会多出性能上报请求。

### 验证

- 本地禁用上报或打到 dev endpoint。
- 线上检查是否收到匿名聚合指标。
- 对比 Cloudflare Worker 数据和浏览器 RUM 数据是否能关联到路由。

---

## 推荐实施顺序

### 第 0 阶段：前置修复（立即执行）

1. 修正 `next.config.ts`，恢复 `pnpm build`。
2. 确认 `pnpm dev` 下 Cloudflare binding 正常。

### 第 1 阶段：基础缓存与并行化

1. 给首页 `listRunSummaries()` 增加 `unstable_cache()`，TTL 300s。
2. 详情页 bootstrap 并行化：current.json 与 access 并发请求。
3. `bootstrap.sfw.json` 改为 `cache: "force-cache"`（资源不可变）。
4. `/api/private-object` 增加 `If-None-Match` → 304 条件返回。
5. `/api/private-object` 按 `.json` 后缀与图片变体分离 `Cache-Control`。

这一阶段预期能改善首页 TTFB，减少详情页重复访问时的 row JSON 成本；登录 SFW 的 Advance 展示必须保持不变。

### 第 2 阶段：交互与请求调度

1. 给 row JSON 请求加并发队列（`maxConcurrent: 4~6`）。
2. 收藏列表改为延后加载（`requestIdleCallback` / `setTimeout`）。
3. 前端 row cache 跨导航复用（模块级内存缓存）。

这一阶段会改变部分内部交互时序，需要更完整的 E2E 和手动浏览器验证。

### 第 3 阶段：长期可观测与结构收敛

1. 接入 RUM。
2. root layout 认证读取瘦身（仅 session cookie 存在时 SSR 读取 user）。
3. 清理未使用 UI primitive 与依赖。
4. 评估是否执行 `DEFERRED_HIGH_RISK_ITEMS.md` 中的远期项目。

---

## 回归测试清单

- 首页匿名访问：模型卡片、封面图、主页缩略图、预览弹窗。
- 首页登录后访问：Header 登录态、退出登录。
- 详情页匿名访问：公开 SFW 网格、锁定态、点击受限内容触发登录。
- 详情页登录 SFW：`auth_sfw` row JSON 路径、Advance 展示、收藏入口、搜索、跳转、复制。
- 详情页登录 NSFW：access grant、私有 bootstrap、私有 row JSON、私有图片代理。
- 工作流下载：登录态权限仍正确。
- 删除 run 后：首页缓存过期或 revalidate 后卡片消失，详情页进入 404/空态。
- Safari：首页卡片 hover、详情页 sticky 表头。
- 移动端：首页滚动、详情页虚拟网格、弹窗尺寸。

---

## 验证命令

```bash
pnpm build
pnpm lint
pnpm test:e2e
uv run pytest -q
```

如果修改涉及 Supabase schema 或上传产物：

```bash
supabase db reset
uv run python -m scripts.r2_upload.upload_images_to_r2 --dry-run --run-dir comfyui_api_outputs/run-xxx
```

---

## 上线后观测

上线后建议至少观察 24 小时：

- Cloudflare `GET /` wall time 和 CPU。
- Cloudflare `/api/private-object` 请求数、304 占比、403 数、慢请求样本。
- 详情页模型路由 RSC 请求 wall time。
- 收藏 API canceled 请求数量。
- RUM 中首页 LCP、详情页 INP、CLS。

成功标准建议：

- `GET /` 慢请求明显减少。
- 登录 SFW 详情页仍显示 Advance，`/api/private-object` 慢请求占比或重复下载量明显下降。
- 详情页首批可视 row ready 时间下降。
- 首页和详情页无权限回退、图片缺失、布局跳动回归。
