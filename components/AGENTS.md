# components/ — 前端组件（业务 + 基础 UI）

## 概览

- `components/` 放组合/业务组件；基础组件集中在 `components/ui/`（shadcn/radix，约定见 `components/ui/AGENTS.md`）。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| 虚拟网格 + 预览 | `components/comfyui/virtual-grid.tsx` | 虚拟滚动 + R2 图片源 + sticky 表头 + 弹窗预览 |
| Blurhash 占位渲染 | `components/comfyui/blurhash-canvas.tsx` | canvas 渲染 blurhash 编码 |
| 网格图片组件 | `components/comfyui/grid-image.tsx` | R2 图片 + blurhash 占位 + 加载状态 |
| ComfyUI 领域组件约定 | `components/comfyui/AGENTS.md` | 性能/交互/图片路径约定 |
| UI 组件使用示例 | `components/component-example.tsx` | 用于展示/验证 UI primitives |
| shadcn 配置 | `components.json` | aliases、style、cssVariables 等 |

## 约定（本目录特有）

- 业务组件优先复用 `components/ui/*` primitives（Button/Dialog/Card/Table/Skeleton 等）
- 图片源：优先使用 R2 公开 URL（`lib/r2-url.ts`）；私有图片通过 `/api/r2/private/` 代理
- 性能：大网格依赖虚拟化（`@tanstack/react-virtual`），避免一次性渲染全部 cell
- Blurhash：图片加载前展示 blurhash 占位（`blurhash-canvas.tsx`），提升感知加载速度

## 反模式

- 不要把 `components/ui/` 当业务逻辑堆放点；业务逻辑应留在 `components/comfyui` 或页面层
- 不要在组件里硬编码文件系统根路径（所有文件读取都在 `lib/` + API route）
- 不要在组件中直接拼接 R2 URL；使用 `lib/r2-url.ts` 构建
