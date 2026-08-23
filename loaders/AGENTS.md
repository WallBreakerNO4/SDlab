<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-19 | Updated: 2026-08-23 -->

# loaders/ — 自定义 Webpack Loader 与构建脚本

## 概览

- 存放 Next.js/Webpack 构建管道所需的自定义 loader 与数据构建脚本：Markdown 源文件加载器、Prompt 法典 JSON 产物生成、模型引导（model guide）元数据生成。

## 关键文件

| 文件 | 描述 |
|------|------|
| `markdown-source-loader.cjs` | 将 `.md` 文件内容导出为字符串，供 `react-markdown` 等组件在构建时内联使用 |
| `prompt-data-builder.ts`     | Prompt 数据构建脚本:读取 `data/prompt-codex/*.yaml` → 生成 `public/data/prompts/*.json`;用 `pnpm tsx` 运行;类型与 `lib/prompt-types.ts` 共享 |
| `model-guide-data-builder.ts` | 模型引导构建脚本:读取 `data/model-guides/*.md` 元数据 → 生成 `lib/generated/model-guides.ts`（`server-only` 模块,供 sitemap 消费）;用 `pnpm guides:build` 运行 |

## 约定（本目录特有）

- Webpack loader 文件使用 CommonJS（`.cjs`）格式。
- 在 `next.config.ts` 中通过 `webpack.module.rules` 注册使用。
- 不要在 loader 中引入异步逻辑或外部依赖，保持无副作用纯转换。
- 数据构建脚本（`*-data-builder.ts`）的产物是提交到仓库的生成文件：`public/data/prompts/*.json` 与 `lib/generated/*.ts`。

## 反模式

- 不要在 loader 中执行文件系统写操作或修改 `this._module` 等 Webpack 内部属性。
- 不要把 loader 用于非构建时数据转换（如运行时 API 调用）。
