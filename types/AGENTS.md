<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-06-18 -->

# types/ — Next.js 生成类型（只读）

## 概览

- `types/` 里包含 Next.js 自动生成的类型与校验文件（`routes.d.ts`、`validator.ts`,文件头会写明 “generated automatically / do not edit”）,以及手写的 cacheLife 模块类型声明（`cache-life.d.ts`）。

## 约定

- 不要手改：`types/routes.d.ts`、`types/validator.ts`（以及同类自动生成文件）
- `types/cache-life.d.ts` 是手写的 Next.js cacheLife 模块类型声明（`declare module 'next/cache'`）,非自动生成;如需扩展 cache 相关类型可在此文件追加
- ESLint 已对这些文件做 ignore（见 `eslint.config.mjs`），变更应通过 Next.js 重新生成（通常在 `pnpm dev`/`pnpm build` 过程中）

## 反模式

- 不要在这些文件里修类型错误；应回到实际页面/API 源码修正
