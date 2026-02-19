# components/comfyui/ — ComfyUI 业务组件

## 概览

- ComfyUI viewer 的业务组件层：网格渲染、预览交互等；依赖 `components/ui/*` primitives；图片一律走 `/api/comfyui/image/...`。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| 虚拟网格 + 预览 | `components/comfyui/virtual-grid.tsx` | `@tanstack/react-virtual` + Dialog + 复制/切图 |
| 页面侧消费 | `app/runs/[runDir]/page.tsx` | 负责 fetch + type guard + skeleton/empty 状态 |

## 约定（本目录特有）

- 性能：大网格必须虚拟化渲染（只渲染可视行/列）；避免一次性 render 全量 cell（E2E 有回归覆盖）。
- 图片 src：用 `toImageSrc(runDir, localImagePath)` 生成 `/api/comfyui/image/...`；不要在组件里假设磁盘路径或直接拼接 `comfyui_api_outputs`。
- 多图：优先合并 `local_image_paths` 与 `local_image_path`（去重、过滤空值），保证预览能正确遍历。
- 状态：仅使用 `success/failed/skipped/missing`；缺失 cell 也要有可渲染占位。
- UI primitives：按钮/对话框等交互来自 `components/ui/*`（不要在业务组件里手写 primitives）。

## 反模式

- 不要在组件内读取文件系统或调用 `lib/comfyui-fs.ts`（数据从页面/API 来）。
- 不要移除虚拟化或把网格渲染改成全量 DOM（性能会退化）。
