# hooks/ — 前端复用 hooks

## 概览

- 本目录只放“跨组件可复用行为”，当前以 `use-mobile.ts` 为主。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| 移动端断点判断 | `hooks/use-mobile.ts` | 基于 `matchMedia`，带事件订阅与清理 |

## 约定（本目录特有）

- hook 只封装行为，不读取业务数据文件、不发起 ComfyUI 相关 I/O。
- 命名以 `use*` 开头，返回值保持语义稳定（避免同名 hook 改变返回形态）。
- 涉及浏览器 API 时必须有 cleanup（如 `removeEventListener`）。

## 反模式

- 不要把页面级状态管理放进这里（例如 run 详情拉取流程）。
- 不要在 hook 中拼接文件系统路径或调用 Node API 路由内部实现。
