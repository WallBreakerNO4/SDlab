<!-- Parent: ../../AGENTS.md -->
<!-- Generated: 2026-04-25 | Updated: 2026-08-23 -->

# app/models/[runDir]/ — 模型详情页共享组件

## 概览

- 模型详情页的客户端组件模块：按 current view → access grant → bootstrap 的顺序建立页面数据，再按可见行拉取 row manifest；渲染虚拟网格 + 模型描述 header + workflow 下载入口。支持 NSFW 视图切换（经 `useUserPreferences()`）。
- 本目录组件由 `app/[locale]/models/[runDir]/page.tsx`（Server Component）消费，不是独立页面路由。

## 去哪儿看

| 场景                   | 位置                           | 备注                                                                        |
| ---------------------- | ------------------------------ | --------------------------------------------------------------------------- |
| 服务端页面入口         | `app/[locale]/models/[runDir]/page.tsx` | Server Component；`params: Promise<{ locale, runDir }>`，校验 `hasLocale()` + `isValidRunDir()` |
| 客户端状态与渲染       | `model-detail-client.tsx`      | 消费 `useModelDetailData`，状态机：loading / ready / not-found / error  |
| 数据拉取 hook          | `use-model-detail-data.ts`     | 拉取 view/current.json → access → bootstrap，含 abort 清理与 type guard    |
| 网格收藏 hook          | `use-style-favorites.ts`       | `useStyleFavorites()`：favoriteKeys + 乐观 toggle（失败回滚 + toast）；style-items 惰性拉取 |
| 模型详情 Header        | `model-detail-header.tsx`      | 模型名、描述、外部链接（homepage/HuggingFace/Civitai）、workflow 下载入口   |
| 类型守卫与响应类型     | `model-detail-types.ts`        | `ModelDetailResponse`、`RunViewAccess`、`CurrentRunView` 及相关 `is*` 守卫  |
| skeleton 占位组件      | `model-detail-skeletons.tsx`   | `SummarySkeleton` + `GridSkeleton`                                          |
| 虚拟网格渲染            | `components/comfyui/virtual-grid.tsx` | 主网格渲染组件                                                    |
| Grid 图片               | `components/comfyui/grid-image.tsx`  | R2 图片 + blurhash 占位                                            |

## 约定（本目录特有）

- 本目录只放客户端组件和类型，不作为独立页面路由；页面入口在 `app/[locale]/models/[runDir]/page.tsx`。
- `use-model-detail-data.ts` 是本页面核心数据 hook：先拉 `view/current.json`（公开）→ 认证用户再拉 `/api/comfyui/run/{runDir}/access` → 最后拉 bootstrap JSON。
- bootstrap 只包含 detail + grid 索引/占位数据；实际 row manifest 由 `components/comfyui/use-virtual-grid-rows.ts` 根据可见行按需加载。
- SFW 场景 bootstrap 通过 `publicObjectUrl()`；NSFW 场景通过 `privateObjectProxyUrl()` + grant token。
- bootstrap JSON 的 `yLabels` / `yPromptParts`（camelCase）会被归一化为 `y_labels` / `y_prompt_parts`（snake_case）以匹配网格组件预期。
- current 缓存与登录态 access grant 的 `release_id` 不一致时，数据 hook 会带 release cache-buster 绕过缓存重拉一次 current。
- 所有 fetch 通过 `AbortController` 管理，组件卸载时自动取消。
- `model-detail-types.ts` 中包含多层 type guard（`isModelDetailResponse` / `isRunGridIndexData` / `isCurrentRunView` / `isRunViewAccess`），服务端返回数据必须经过校验才进入渲染态。
- 认证入口统一走 `AuthProvider` + `useAuth()`；workflow 下载需要登录态。
- 收藏 hook 放本目录（`hooks/` 目录约定不放页面级业务数据 hook）；共享类型/guard 与薄 fetch/mutate 函数在 `lib/style-favorites.ts`。

## 反模式

- 不要绕过 type guard 直接消费 API 返回值；所有 fetch 结果都经 `is*` 守卫校验。
- 不要在本目录中创建新的 `page.tsx` 作为路由入口；页面入口位于 `app/[locale]/models/[runDir]/page.tsx`。
- 不要手动拼接 bootstrap URL 或 R2 路径；使用 `publicObjectUrl()` / `privateObjectProxyUrl()`。
- 不要把展示页缩略图语义用于此页面的首页卡片展示。
- 不要在这里引入 `server-only` 的 Supabase auth client。
