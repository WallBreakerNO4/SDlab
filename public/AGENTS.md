<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-18 | Updated: 2026-06-18 -->

# public/ — Next.js 静态资源根

## 概览

- Next.js 公开静态资源目录:站点 favicon、Prompt 法典浏览器消费的 JSON 构建产物、以及 Next 默认占位 svg。运行时通过站点根路径 `/` 直接访问,不参与编译。

## 去哪儿看

| 场景 | 位置 | 备注 |
|------|------|------|
| 站点 favicon | `favicon/` | `favicon.svg` / `favicon.ico` / `apple-touch-icon.png` / `site.webmanifest` 等多尺寸图标,由 `app/[locale]/layout.tsx` metadata icons 引用 |
| Prompt 法典 JSON 产物 | `data/prompts/index.json`、`data/prompts/files/*.json` | 构建期由 `loaders/prompt-data-builder.ts` 从 `data/prompt-codex/*.yaml` 生成;运行时由 `lib/prompt-data-loader.ts` 通过 `fetch("/data/prompts/...")` 加载 |
| Next 默认占位 svg | `file.svg`、`globe.svg`、`next.svg`、`vercel.svg`、`window.svg` | Next.js 脚手架自带,可按需清理 |

## 约定（本目录特有）

- `public/data/prompts/*.json` 是**构建产物**,不是手写源资产;源资产在 `data/prompt-codex/*.yaml`。改 schema 时应更新源 YAML 后重新跑构建脚本,不要直接编辑本目录 JSON。
- 法典 JSON 产物由 `loaders/prompt-data-builder.ts` 生成,类型与 `lib/prompt-types.ts` 共享;运行时只读不写。
- favicon 资源由 `app/[locale]/layout.tsx` 通过 metadata `icons` 字段引用。

## 反模式

- 不要把运行产物或用户数据写进 `public/`;它只放版本化静态资源与构建期产物。
- 不要手动编辑 `public/data/prompts/*.json`;那是构建产物,改源 YAML 后重新生成。
- 不要把 `public/` 当业务代码目录;它不参与编译,只做静态托管。
