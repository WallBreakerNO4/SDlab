# components/ — 前端组件（业务 + 基础 UI）

## 概览

- `components/` 放组合/业务组件；基础组件集中在 `components/ui/`（shadcn/radix，约定见 `components/ui/AGENTS.md`）。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| ComfyUI 网格渲染与预览 | `components/comfyui/virtual-grid.tsx` | 虚拟滚动、sticky 表头、弹窗预览 |
| ComfyUI 领域组件约定 | `components/comfyui/AGENTS.md` | VirtualGrid 性能/交互/图片路径约定 |
| UI 组件使用示例 | `components/component-example.tsx` | 用于展示/验证 UI primitives |
| shadcn 配置 | `components.json` | aliases、style、cssVariables 等 |

## 约定（本目录特有）

- 业务组件优先复用 `components/ui/*` primitives（Button/Dialog/Card/Table/Skeleton 等）
- URL 拼接：图片 src 必须走网站 API（`/api/comfyui/image/...`），不要直接假设磁盘路径
- 性能：大网格依赖虚拟化（见 `@tanstack/react-virtual` 的用法），避免一次性渲染全部 cell

## 反模式

- 不要把 `components/ui/` 当业务逻辑堆放点；业务逻辑应留在 `components/comfyui` 或页面层
- 不要在组件里硬编码文件系统根路径（所有文件读取都在 `lib/` + API route）
