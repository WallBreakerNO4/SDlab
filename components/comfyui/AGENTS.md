# components/comfyui/ — ComfyUI 业务组件

## 概览

- ComfyUI viewer 的业务组件层：虚拟网格、图片渲染（含 R2 源 + blurhash 占位）、预览交互。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| 虚拟网格 + 预览 | `virtual-grid.tsx` | `@tanstack/react-virtual` + Dialog + 复制/切图 |
| Blurhash 占位 | `blurhash-canvas.tsx` | 从 blurhash 字符串渲染 canvas 占位图 |
| 网格图片组件 | `grid-image.tsx` | R2 图片 + blurhash 占位 + 加载/错误状态切换 |
| 页面侧消费 | `app/runs/[runDir]/page.tsx` | fetch + type guard + skeleton/empty 状态 |

## 约定（本目录特有）

- 性能：大网格必须虚拟化渲染（只渲染可视行/列）；避免一次性 render 全量 cell
- 图片源：R2 公开 URL 优先；私有图片走 `/api/r2/private/` 代理。URL 构建使用 `lib/r2-url.ts`
- Blurhash：图片未加载时展示 blurhash canvas 占位；加载完成后平滑切换到真实图片
- 多图：优先合并 `local_image_paths` 与 `local_image_path`（去重、过滤空值），保证预览能正确遍历
- 状态：仅使用 `success/failed/skipped/missing`；缺失 cell 也要有可渲染占位
- UI primitives：按钮/对话框等交互来自 `components/ui/*`（不要在业务组件里手写 primitives）

## 反模式

- 不要在组件内读取文件系统或调用 `lib/comfyui-fs.ts`（数据从页面/API 来）
- 不要移除虚拟化或把网格渲染改成全量 DOM
- 不要在组件中自行拼接 R2 URL 或磁盘路径
