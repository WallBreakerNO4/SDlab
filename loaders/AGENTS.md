<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-19 | Updated: 2026-05-19 -->

# loaders/ — 自定义 Webpack Loader

## 概览

- 存放 Next.js/Webpack 构建管道所需的自定义 loader，当前仅含 Markdown 源文件加载器。

## 关键文件

| 文件 | 描述 |
|------|------|
| `markdown-source-loader.cjs` | 将 `.md` 文件内容导出为字符串，供 `react-markdown` 等组件在构建时内联使用 |

## 约定（本目录特有）

- 文件为 CommonJS（`.cjs`），因为 Webpack loader 在 ESM 环境下存在兼容性限制。
- 在 `next.config.ts` 中通过 `webpack.module.rules` 注册使用。
- 不要在 loader 中引入异步逻辑或外部依赖，保持无副作用纯转换。

## 反模式

- 不要在 loader 中执行文件系统写操作或修改 `this._module` 等 Webpack 内部属性。
- 不要把 loader 用于非构建时数据转换（如运行时 API 调用）。
