<!-- Parent: ../../AGENTS.md -->
<!-- Generated: 2026-04-25 | Updated: 2026-04-25 -->

# app/privacy-policy/ — 隐私权政策页面

## 概览

- 简单的静态 Markdown 渲染页面："隐私权政策"。

## 去哪儿看

| 场景          | 位置                          | 备注                                                                 |
| ------------- | ----------------------------- | -------------------------------------------------------------------- |
| 隐私政策页    | `page.tsx`                    | `force-static`，用 `react-markdown` 渲染 `data/privacy-policy-page.md` |
| Markdown 源   | `data/privacy-policy-page.md` | 页面内容 Markdown 文件                                                |

## 约定（本目录特有）

- `export const dynamic = "force-static"`，页面在构建时预渲染。
- 使用 `react-markdown` 渲染 Markdown 内容，样式由全局 `.prose-custom` 控制。
- 不要在此页面引入 Supabase、认证或动态数据查询逻辑。

## 反模式

- 不要把此页面改成动态渲染或引入运行时数据源。
- 不要在此处内联大段 Markdown 文案；应更新 `data/privacy-policy-page.md`。
