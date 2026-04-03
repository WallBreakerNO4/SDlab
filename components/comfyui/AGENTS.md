# components/comfyui/ — ComfyUI 业务组件

## 概览

- ComfyUI viewer 的业务组件层：虚拟网格、图片渲染（含 R2 源 + blurhash 占位）、预览交互。
- 术语约定：本目录处理的 `display_*` / `thumb_*` 变体统一称为“展示页缩略图”；不要把未来首页卡片的“主页缩略图”概念混进这里。

## 去哪儿看

| 场景            | 位置                         | 备注                                           |
| --------------- | ---------------------------- | ---------------------------------------------- |
| 虚拟网格 + 预览 | `virtual-grid.tsx`           | `@tanstack/react-virtual` + Dialog + 复制/切图 |
| Blurhash 占位   | `blurhash-canvas.tsx`        | 从 blurhash 字符串渲染 canvas 占位图           |
| 网格图片组件    | `grid-image.tsx`             | R2 图片 + blurhash 占位 + 加载/错误状态        |
| 页面侧消费      | `app/runs/[runDir]/page.tsx` | fetch + type guard + skeleton/empty 状态       |

## 约定（本目录特有）

- 性能：大网格必须虚拟化渲染（只渲染可视行/列）；避免一次性 render 全量 cell。
- 图片源：R2 公开 URL 优先；私有图片使用 `privateObjectUrl()` 生成的短期签名 URL。URL 构建使用 `lib/r2-url.ts`。
- Blurhash：图片未加载时展示 blurhash canvas 占位；加载完成后平滑切换到真实图片。
- 多图：预览数据来自 `/row` 返回的 `items[].thumb` / `display`；展示时优先选可用 display/thumb 变体。这些变体在文档中统一称为“展示页缩略图”。
- 状态：组件层核心是 row cache 的 `ready/error` 与图片加载中的占位态；缺失 cell 也要能渲染 blurhash 或空态。
- UI primitives：按钮/对话框等交互来自 `components/ui/*`，不要在业务组件里手写 primitives。

## 反模式

- 不要在组件内读取文件系统或绕过页面/API 直接访问数据层。
- 不要移除虚拟化或把网格渲染改成全量 DOM。
- 不要在组件中自行拼接 R2 URL 或磁盘路径。
