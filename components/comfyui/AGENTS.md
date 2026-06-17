<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-06-18 -->

# components/comfyui/ — ComfyUI 业务组件

## 概览

- ComfyUI viewer 的业务组件层：虚拟网格、图片渲染（含 R2 源 + blurhash 占位）、预览交互。
- 术语约定：本目录处理的 `display_*` / `thumb_*` 变体统一称为“展示页缩略图”；不要把首页卡片的“主页缩略图”概念混进这里。

## 去哪儿看

| 场景            | 位置                         | 备注                                           |
| --------------- | ---------------------------- | ---------------------------------------------- |
| 虚拟网格 + 预览 | `virtual-grid.tsx`           | `@tanstack/react-virtual` + Dialog + 复制/切图 |
| Blurhash 占位   | `blurhash-canvas.tsx`        | 从 blurhash 字符串渲染 canvas 占位图           |
| 网格图片组件    | `grid-image.tsx`             | R2 图片 + blurhash 占位 + 加载/错误状态        |
| 页面侧消费      | `app/[locale]/models/[runDir]/page.tsx` | Server Component → `ModelDetailClientPage` → 虚拟网格       |
| 虚拟网格布局/行/滚动 hook | `use-virtual-grid-layout.ts`、`use-virtual-grid-rows.ts`、`use-virtual-grid-scroll.ts` | 计算可视行/列、构建行缓存、滚动位置管理与恢复 |
| 列显隐 hook              | `use-column-visibility.ts`                                | 网格 X 列显示/隐藏,localStorage 持久化 |
| 变体源选择 hook          | `use-renderable-variant-source.ts`                        | 按公开/私有选择图片源,走 `private-image-cache` 或 `publicObjectUrl()` |
| 单元格预览弹窗           | `virtual-grid-cell-dialog.tsx`                            | 复制 prompt / 下载图片 / 翻页 |
| 单元格/行标签组件        | `virtual-grid-preview-cell.tsx`、`virtual-grid-row-label.tsx` | 预览单元格(`GridImage` + `pickBestVariants`)/ Y 轴行标签 |
| 网格类型与工具           | `virtual-grid-types.ts`、`virtual-grid-utils.ts`          | `ImageVariantSource` / `CachedRow` 等共享类型 + `pickBestVariants()` 等工具 |

## 约定（本目录特有）

- 性能：大网格必须虚拟化渲染（只渲染可视行/列）；避免一次性 render 全量 cell。
- 图片源：R2 公开 URL 优先；私有图片使用 `privateObjectUrl()` 生成的短期签名 URL。URL 构建使用 `lib/r2-url.ts`。
- Blurhash：图片未加载时展示 blurhash canvas 占位；加载完成后平滑切换到真实图片。
- 多图：表格缩略图数据来自 `/row` 返回的 `items[].thumb`；弹窗大图通过 `/display` 按需获取 fresh URL，只认 display 变体，不做 thumb 回退，也不要在 row 预取阶段缓存 display 签名。
- 状态：组件层核心是 row cache 的 `ready/error` 与图片加载中的占位态；缺失 cell 也要能渲染 blurhash 或空态。
- UI primitives：按钮/对话框等交互来自 `components/ui/*`，不要在业务组件里手写 primitives。

## 反模式

- 不要在组件内读取文件系统或绕过页面/API 直接访问数据层。
- 不要移除虚拟化或把网格渲染改成全量 DOM。
- 不要在组件中自行拼接 R2 URL 或磁盘路径。
