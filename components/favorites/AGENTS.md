<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-07-20 | Updated: 2026-08-23 -->

# components/favorites/ — 收藏与模型对比客户端 UI

## 概览

- 本目录实现登录用户的画师串收藏工作区：收藏目录分页、已发布模型显隐、同风格跨模型矩阵、单收藏详情和私有图片预览。
- 数据通过 `/api/viewer/style-comparison` 目录/详情/slice API 与 R2 私有 row JSON 组合，不直接访问 Supabase。

## Key Files

| 文件 | 描述 |
| --- | --- |
| `favorites-page.tsx` | 收藏矩阵主工作区：登录门控、分页、模型显隐、slice/row 加载、预览和取消收藏 |
| `favorite-comparison-detail.tsx` | 单个 `style_key` 跨模型、跨 X 测试场景的详情矩阵 |
| `comparison-loader.ts` | 目录/slice fetch、私有 row URL、row cache 与有界并发加载 |

## For AI Agents

### Working In This Directory

- 登录态统一消费 `useAuth()`；未登录显示 `AuthLoginDialog`，不要在客户端创建 Supabase client 或绕过 viewer API。
- 对比目录每页最多 40 条；slice 每次最多提交 40 个 style keys 和 12 个 run dirs。客户端切片只能进一步收紧上限，不能放宽服务端边界。
- 所有 placement 的 `y_index` 均为 0-based，并直接对应 `rows/{viewer_variant}/{y_index}.json`；不要为 UI 展示提前改成 1-based。
- 首次目录响应携带模型目录，后续 cursor 页只合并收藏；隐藏模型状态存于 `sdlab:favorites:hidden-models`，模型集合变化后必须清理失效 runDir。
- `comparison-loader.ts` 的 row cache key 包含 `runDir/releaseId/viewerVariant/yIndex`；grant 刷新不应改变同一对象的 row cache 身份。
- row manifest 的 `items[].blurhash` 是可选字段：item 级缺失时使用 slice placement 的 `blurhashes: [x_index, batch_index, blurhash][]` 回退。前端为 slice BlurHash 构建 `run/y/x/batch` lookup，row item 自带值始终优先。
- row 状态必须区分 `loading` 与 `missing`：有 placement 且 row 请求仍在进行时保持 loading，占位可由 Skeleton/BlurHash 承接；只有确认该模型无 placement 时才是 missing，不能在异步请求尚未完成时提前显示“暂无图片”。
- 私有 row/图片必须使用 slice 返回的 grant 和 `privateObjectProxyUrl()`；API route 先授权再访问共享 edge cache，cache URL 去除 grant 但保留对象 key，客户端不得自行模拟该流程。
- 图片渲染复用 `GridImage` 与 `useRenderableVariantSource()`；公开/私有变体选择、object URL 生命周期继续遵守 `components/comfyui/AGENTS.md`。
- `showNsfw` 变化后重新请求 slice，使 `viewer_variant`、grant 与 slice BlurHash 同步；slice 状态必须绑定 variant，切换后不能继续读取旧 variant 的 BlurHash。不要在客户端自行推断未授权的 NSFW 路径。

### Testing Requirements

- `pnpm test` 已覆盖 slice RPC guard、row manifest BlurHash 新旧兼容、slice BlurHash lookup 和 loading/missing/ready/error 状态；模型 merge/显隐/reconcile 与 row slide 排序仍需在修改时补对应测试。
- 修改 `mergeComparisonFavorites()`、`getVisibleModels()`、`reconcileHiddenRunDirs()`、`flattenRowSlides()` 或 placement/row 逻辑时，应补对应单测，并明确验证 0-based `y_index`。
- 修改交互后至少运行 `pnpm lint` 与 `pnpm typecheck`；模型对比 E2E 覆盖 manifest 缺失 BlurHash 时使用 slice BlurHash 回退的总览与单收藏详情路径。

### Common Patterns

- catalog 与 slice 请求使用 `cache: "no-store"`；私有 row fetch 携带 grant，本地 row cache 通过稳定的 run/release/variant/y 身份复用响应。
- 异步加载持有 `AbortController`，组件卸载或输入变化时取消旧请求；批量 row 加载使用有界并发。
- 多语言文案统一来自 `useTranslations("styleFavorites")`，导航统一使用 `@/i18n/navigation`。

## Dependencies

### Internal

- `lib/style-comparison.ts` - 对比类型、guard、游标与客户端纯函数
- `lib/style-favorites.ts` - 收藏删除与 `style_key` 合约
- `components/comfyui/` - 图片渲染、变体选择与 row payload 标准化
- `components/auth-provider.tsx`、`components/user-preferences-provider.tsx` - 登录态与 NSFW 偏好

### External

- `next-intl` - 收藏与模型对比文案
- `lucide-react`、`components/ui/` - 交互图标与 UI primitives
