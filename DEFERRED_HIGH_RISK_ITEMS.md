# 高风险延迟项目（独立专项）

<!-- Generated: 2026-05-13 -->

## 来源

以下项目从 `PERFORMANCE_OPTIMIZATION_PLAN.md` 中拆分，原因是改动范围过大、涉及安全架构变更、或存在显著的 Safari/浏览器回归风险。每项应作为**独立专项**进行设计、实现和验证，不应与当前阶段的缓存/并行化优化混合上线。

---

## 项目 A：grant 从 query string 迁移到 header/cookie

**来源**：原 P0-2.5（登录态 SFW 私有行 JSON 降本）

### 当前状态

`components/comfyui/use-virtual-grid-rows.ts:34-38` 中，`buildRowManifestUrl()` 对 auth_sfw / auth_nsfw 使用 `privateObjectProxyUrl()`，该函数将 grant token 放入 URL query string：

```ts
// lib/r2-url.ts:27-32
export function privateObjectProxyUrl(r2Key: string, grant: string): string {
  validateR2Key(r2Key);
  const url = new URL("/api/private-object", "http://localhost");
  url.searchParams.set("key", r2Key);
  url.searchParams.set("grant", grant);
  return `${url.pathname}${url.search}`;
}
```

带来的问题：
- grant 是短期 token，轮换后 URL 完全变化。
- 浏览器 HTTP cache 以完整 URL 为 key，因此 grant 轮换后无法命中缓存，即使 row JSON 内容未变。
- 同一用户多次访问同一行时，每次都需重新下载完整 row JSON payload。

### 目标

将 grant 从 URL query string 迁移到 HTTP header（`Authorization: Bearer <grant>`）或 httpOnly cookie，使 row JSON 的请求 URL 保持稳定（仅含 R2 key），从而允许浏览器利用条件请求（ETag/If-None-Match）和私有缓存。

### 受影响范围

| 层次 | 文件 | 改动内容 |
| --- | --- | --- |
| URL 构建 | `lib/r2-url.ts` | `privateObjectProxyUrl()` 不再拼接 grant 到 URL |
| 前端 fetch | `components/comfyui/use-virtual-grid-rows.ts` | `buildRowManifestUrl()` 返回不带 grant 的 URL；`requestRow()` 在 fetch headers 中加入 grant |
| 前端 fetch（图片） | `components/comfyui/grid-image.tsx` | 私有图片 URL 同样不再含 grant，fetch 时通过 header 传递 |
| Route handler | `app/api/private-object/route.ts` | 从 `Authorization` header 或 cookie 读取 grant 替代 `searchParams.get("grant")` |
| 其他调用方 | `app/models/[runDir]/use-model-detail-data.ts`、所有使用 `privateObjectProxyUrl()` 的地方 | 调整为 headers 传递 grant |

### 风险与审查要点

1. **安全审查**：grant 从 URL 移到 header 是否引入新的 CSRF/点击劫持风险？当前 query string 方案是否有已知的安全依赖？
2. **Service Worker / CDN 行为**：Cloudflare CDN 默认不缓存带 `Authorization` header 的请求，这符合预期。但如果未来引入 SW，需确认不会错误缓存。
3. **浏览器兼容性**：`fetch` 的 `headers` 选项广泛支持，无兼容性问题。
4. **grant 轮换时序**：如果 grant 在页面打开期间过期并轮换，前端需感知并重发请求。当前通过 URL 变化自然触发重新请求；改为 header 后需要显式的重新请求逻辑。
5. **cookie 方案额外风险**：httpOnly cookie 需要服务端 `Set-Cookie`，会引入 CSRF 保护需求，且可能影响跨域行为。
6. **`verifyRunMediaGrant()` 签名验证**：`scripts/r2_upload/` 和 Web 侧的 grant 生成/消费逻辑需保持一致性。

### 前置条件

- 当前阶段的 ETag/If-None-Match 条件请求（`PERFORMANCE_OPTIMIZATION_PLAN.md` 第 3 项）已完成并上线，作为本项目的性能对比基线。
- 所有使用 `privateObjectProxyUrl()` 的调用方已完成全量梳理。

### 建议实施方案

1. 优先采用 **`Authorization: Bearer <grant>` header 方案**（而非 cookie），改动范围更可控。
2. 新增 `privateObjectKey(r2Key: string): string`（不带 grant 的 URL），保留旧函数兼容过渡。
3. 先改 route handler 同时接受 query string 和 header 两种 grant 传递方式（双通道兼容期）。
4. 前端逐步迁移调用方。
5. 下掉 query string 通道。

---

## 项目 B：row chunk JSON 产物格式变更

**来源**：原 P0-2.6（登录态 SFW 私有行 JSON 降本）

### 当前状态

当前 `scripts/r2_upload/manifest.py` 生成的 row manifest 是每行一个独立 JSON 文件：

```
runs/{run_dir}/view/v2/{release_id}/rows/{viewer_variant}/{y_index}.json
```

对于 128 行的 run，前端需要发出多达 128 次请求（实际受虚拟滚动 overscan 控制，首次约 16~24 次）。每次请求经过 `/api/private-object` 代理 → R2 私有 bucket 读取 → Worker 返回。

### 目标

将 row JSON 打包为 chunk 文件（例如每 8 或 16 行一个 chunk）：

```
runs/{run_dir}/view/v2/{release_id}/rows/{viewer_variant}/chunks/0-15.json
runs/{run_dir}/view/v2/{release_id}/rows/{viewer_variant}/chunks/16-31.json
...
```

前端一次请求可拿到多行数据，大幅减少请求数量。

### 受影响范围

| 层次 | 文件 | 改动内容 |
| --- | --- | --- |
| Manifest 生成 | `scripts/r2_upload/manifest.py` | 新增 chunk 打包逻辑；保留单行 JSON 生成作为 fallback |
| 上传管线 | `scripts/r2_upload/upload_planner.py` | manifest upload 列表中新增 chunk 文件 |
| 前端 row 请求 | `components/comfyui/use-virtual-grid-rows.ts` | `buildRowManifestUrl()` 支持 chunk URL；`requestRow()` 解析 chunk 后填充到单行 cache |
| 前端 row cache | `components/comfyui/use-virtual-grid-rows.ts` | `rowCacheRef` 需要同时处理 chunk 和单行的结果 |
| 类型定义 | `components/comfyui/virtual-grid-types.ts` | 可能新增 chunk response 类型 |

### 风险与审查要点

1. **上传管线兼容性**：必须保留单行 JSON 生成，否则回滚困难。chunk 和单行 JSON 共存时 R2 存储成本上升但可控（row JSON 体积小）。
2. **前端解析复杂度**：chunk 解析需要拆分到各行的 `cellsByX` map，逻辑需与现有 `normalizeRowPayload()` 对齐。
3. **缓存策略**：chunk JSON 的 `Cache-Control` 应与单行 JSON 一致（`private, max-age=300`）。
4. **partial load 场景**：如果 chunk 中部分行数据不合法（404、格式错误），不应 block 其他行的渲染。
5. **与项目 A 的依赖**：如果先完成 grant→header 迁移，chunk URL 的缓存命中率会更高。

### 前置条件

- 项目 A（grant→header 迁移）建议先完成，以获得稳定的 chunk URL 缓存。
- 当前阶段的并发请求队列（`PERFORMANCE_OPTIMIZATION_PLAN.md` 第 4 项）上线后，可先观测单行 JSON 模式下的性能改善幅度，再评估 chunk 是否必要。

### 建议实施方案

1. 第一阶段：上传侧生成 chunk JSON，但前端暂不使用（仅 R2 存储）。
2. 第二阶段：前端增加 chunk 优先策略：先尝试 `chunks/` 路径，404 则 fallback 到单行 JSON。
3. 第三阶段：全部迁移后，评估是否移除单行 JSON 生成。

---

## 项目 C：首页 HorizontalScrollList DOM 收敛与缩略图优化

**来源**：原 P1-6（首页卡片图片与 DOM 数量收敛）

### 当前状态

`components/home/model-card.tsx` 的 `HorizontalScrollList` 组件通过复制缩略图数组实现"无限滚动"效果。复制次数为 `Math.max(5, ceil(20 / assets.length))`。例如 4 个 assets 的场景会产生 5 组 × 4 = 20 个 `<li>` 元素，每个含 `BlurhashCanvas` 和 `<img>`。

首页 `home-page-client.tsx` 是 `"use client"` 组件，所有卡片客户端渲染。

最近一次相关提交 `60d59ba`（2026-04-28）修复了 Safari 卡片布局与 hover 跳位 bug，说明此处的浏览器兼容性敏感。

### 目标

1. 收敛横向缩略图 DOM 数量：从"固定至少 20 项"改为按视口宽度动态计算所需的复制组数。
2. 拆分首页 Server/Client 边界：hero、标题、卡片静态文案留在 Server Component。
3. 首屏封面图加载优先级优化：前 1~3 张卡片封面使用 `loading="eager"` + `fetchPriority="high"`。
4. 缩略图 blurhash 降级：缩略图优先使用 CSS 背景色或轻量 placeholder，仅封面图保留 blurhash canvas。
5. 滚动事件改用 `requestAnimationFrame` 节流。

### 受影响范围

| 层次 | 文件 | 改动内容 |
| --- | --- | --- |
| 首页卡片 | `components/home/model-card.tsx` | `HorizontalScrollList` 复制逻辑、blurhash 条件渲染 |
| 首页客户端页 | `app/home-page-client.tsx` | 拆分为 Server + Client Component |
| 首页页 | `app/page.tsx` | 可能需要调整 Server Component 输出 |

### 风险与审查要点

1. **Safari 兼容性**：`HorizontalScrollList` 的复制数组 + CSS snap scroll 实现在 Safari 上历史问题多（`60d59ba` 刚修过）。任何改动都需：
   - Safari 桌面 + iOS Safari 手动测试。
   - Playwright WebKit（`pnpm test:e2e` 已配置 WebKit 项目时）。
2. **Server/Client 拆分**：拆分后需确保 hydration 一致性。`RunSummary` 数据通过 props 从 Server Component 传递到 Client Component。
3. **Blurhash 降级视觉影响**：缩略图从 blurhash canvas 降级为 CSS 背景色，加载过程的视觉效果会变差（从模糊预览变为纯色块）。需评估是否可接受。
4. **滚动性能**：`requestAnimationFrame` 替代 `setTimeout` 是正确的方向，但需验证不会导致滚动事件堆积。
5. **移动端**：移动端更易受 DOM 数量影响，缩减比例应比桌面端更激进。

### 前置条件

- 当前阶段的上线后观测数据（RUM）可用，作为 DOM 重构前后的对比基线。
- Safari + 移动端的 E2E 测试已补充或手动测试流程已就绪。

### 建议实施方案

1. **拆分子任务，分阶段上线**：
   - 阶段 A：Server/Client 拆分 + 滚动 rAF 优化（低风险，独立上线）。
   - 阶段 B：`loading="eager"` 首屏封面图优先级（低风险，独立上线）。
   - 阶段 C：HorizontalScrollList 复制数量收敛（高风险，需单独上线 + 观测）。
   - 阶段 D：缩略图 blurhash 降级（视觉变更，需设计确认后上线）。

2. 阶段 C 建议同时保留旧实现作为 feature flag，通过 URL 参数或构建时开关切换。

---

## 项目间的依赖关系

```
项目 A (grant→header)
  ├── 影响项目 B (chunk URL 缓存稳定性)
  └── 独立于项目 C

项目 B (row chunk)
  ├── 依赖项目 A 以获得更好的缓存命中
  └── 独立于项目 C

项目 C (DOM convergence)
  └── 独立于项目 A、B
```

建议执行顺序：**A → B → C**（A 和 C 可并行启动，但建议分开上线）。

---

## 验证要求（共同）

- 每项需有独立的 E2E 测试补充。
- 上线需通过 feature flag 或分阶段灰度。
- 每项上线后至少观测 48 小时 Cloudflare + RUM 数据。
- 如涉及上传产物格式变更（项目 B），需先在 staging 环境跑通完整的上传 → Web 消费链路。
