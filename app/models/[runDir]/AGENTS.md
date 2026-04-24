<!-- Parent: ../../AGENTS.md -->
<!-- Generated: 2026-04-25 | Updated: 2026-04-25 -->

# app/models/[runDir]/ — 模型详情页

## 概览

- 模型详情页：并行拉取 run 详情（detail）+ 网格索引（grid），渲染虚拟网格 + 模型描述 header + workflow 下载入口。支持 NSFW 切换、用户风格提示词收藏。

## 去哪儿看

| 场景                   | 位置                           | 备注                                                                        |
| ---------------------- | ------------------------------ | --------------------------------------------------------------------------- |
| 服务端页面入口         | `page.tsx`                     | Server Component；`params: Promise<{ runDir }>`，校验 `isValidRunDir()`     |
| 客户端状态与渲染       | `model-detail-client.tsx`      | `useModelDetailData` 并行拉取，状态机：loading / ready / not-found / error  |
| 数据拉取 hook          | `use-model-detail-data.ts`     | 拉取 view/current.json → access → bootstrap，含 abort 清理与 type guard    |
| 模型详情 Header        | `model-detail-header.tsx`      | 模型名、描述、外部链接（homepage/HuggingFace/Civitai）、workflow 下载入口   |
| 类型守卫与响应类型     | `model-detail-types.ts`        | `ModelDetailResponse`、`RunViewAccess`、`CurrentRunView` 及相关 `is*` 守卫  |
| skeleton 占位组件      | `model-detail-skeletons.tsx`   | `SummarySkeleton` + `GridSkeleton`                                          |
| 风格提示词收藏 hook    | `use-style-prompt-favorites.ts` | 用户登录后的风格 prompt 收藏（增/删/标记使用），调 `/api/viewer/style-prompt-favorites` |
| 虚拟网格渲染            | `components/comfyui/virtual-grid.tsx` | 主网格渲染组件                                                    |
| Grid 图片               | `components/comfyui/grid-image.tsx`  | R2 图片 + blurhash 占位                                            |

## 约定（本目录特有）

- `page.tsx` 是 Server Component，只校验 `runDir` 合法后渲染 `ModelDetailClientPage`；不在此做数据获取。
- `use-model-detail-data.ts` 是本页面核心数据 hook：先拉 `view/current.json`（公开）→ 认证用户再拉 `/api/comfyui/run/{runDir}/access` → 最后拉 bootstrap JSON。
- SFW 场景 bootstrap 通过 `publicObjectUrl()`；NSFW 场景通过 `privateObjectProxyUrl()` + grant token。
- bootstrap JSON 的 `yLabels`（camelCase）会被归一化为 `y_labels`（snake_case）以匹配网格组件预期。
- 所有 fetch 通过 `AbortController` 管理，组件卸载时自动取消。
- `model-detail-types.ts` 中包含多层 type guard（`isModelDetailResponse` / `isRunGridIndexData` / `isCurrentRunView` / `isRunViewAccess`），服务端返回数据必须经过校验才进入渲染态。
- style prompt favorites 功能仅登录用户可用，通过 `useStylePromptFavorites` hook 管理。
- 认证入口统一走 `AuthProvider` + `useAuth()`；workflow 下载需要登录态。

## 反模式

- 不要绕过 type guard 直接消费 API 返回值；所有 fetch 结果都经 `is*` 守卫校验。
- 不要在 `page.tsx` 中做数据获取；所有数据逻辑应由 client component 的 hook 负责。
- 不要手动拼接 bootstrap URL 或 R2 路径；使用 `publicObjectUrl()` / `privateObjectProxyUrl()`。
- 不要把展示页缩略图语义用于此页面的首页卡片展示。
- 不要在这里引入 `server-only` 的 Supabase auth client。
