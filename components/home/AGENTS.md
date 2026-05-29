<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-25 | Updated: 2026-05-30 -->

# components/home/ — 首页模型卡片组件

## 概览

- 首页（`app/[locale]/page.tsx` + `app/home-page-client.tsx`）使用的模型卡片组件：封面图展示、描述展开/收起、主页缩略图水平卷轴与预览弹窗。

## 去哪儿看

| 场景             | 位置                     | 备注                                                                                |
| ---------------- | ------------------------ | ----------------------------------------------------------------------------------- |
| 模型卡片         | `model-card.tsx`         | 封面图（cover）+ 描述展开收起 + 主页缩略图水平卷轴（HorizontalScrollList）          |
| 预览大图弹窗     | `preview-dialog.tsx`     | 全屏大图预览，基于 `components/ui/dialog.tsx`；点击关闭                             |
| 封面图/主页缩略图 | `API: /api/comfyui/runs` | 首页 runs 列表返回 `assets.cover` 与 `assets.homepage_cards`                        |
| 图片源构建       | `lib/r2-url.ts`          | R2 公开 URL 生成                                                                    |
| Blurhash 占位    | `components/comfyui/blurhash-canvas.tsx` | 用于封面图/缩略图加载占位                                            |

## 约定（本目录特有）

- 封面图（cover）来自 `assets.cover`，统一走 `resolvePreferredImageSource()` 优先选 display → thumb 降级。
- 主页缩略图（homepage_cards）来自 `assets.homepage_cards[]`，同样走 display/thumb 降级。
- `CardImage` 子组件使用 `<picture>` + `<source>` 支持 avif/webp 格式，配合 blurhash canvas 做加载占位。
- `HorizontalScrollList` 实现无限滚动效果：通过 `copyCount` 份循环复制 + 滚动位置归位（middleCopyIndex），支持左右箭头按钮与平滑滚动。
- 描述 `ExpandableDescription` 检测文本是否溢出（`scrollHeight > clientHeight`），按需提供展开/收起按钮。
- 这些组件只消费 Supabase + R2 返回的 URL 数据，不直接访问数据层。
- 封面图/主页缩略图属于首页独立资产，不要与 run 详情页的展示页缩略图混用。

## 反模式

- 不要在这些组件中直接拼 R2 URL 或磁盘路径。
- 不要把首页卡片资产（封面图/主页缩略图）语义直接映射为展示页缩略图。
- 不要在卡片组件中引入服务端 Supabase client。
