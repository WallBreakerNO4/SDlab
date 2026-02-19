# app/api/comfyui/ — ComfyUI 产物读取 API（Node runtime）

## 概览

- App Router route handlers：只读 `comfyui_api_outputs/`（经 `lib/` 解析与校验），不调用 Python。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| runs 列表 | `app/api/comfyui/runs/route.ts` | 返回最小化 summaries（数组） |
| run 详情 | `app/api/comfyui/run/[runDir]/route.ts` | 校验 runDir；返回 `{ run, xLabels, yLabels }` |
| grid 索引 | `app/api/comfyui/run/[runDir]/grid/route.ts` | `cells` 经过 payload 收敛（适配虚拟网格） |
| 图片代理 | `app/api/comfyui/image/[runDir]/[...imagePath]/route.ts` | 路径安全链 + stream + cache-control |

## 约定（本目录特有）

- 运行时：每个 `route.ts` 必须保持 `export const runtime = "nodejs"`（依赖 fs/stream）。
- 校验顺序：`discoverRunDirs()` → `assertAllowedRunDir()`；图片额外 `assertSafeRelativeImagePath()` → `resolvePathUnderRoot()`。
- 错误响应：404 仅用于“不存在/非法输入”；500 用固定短文案；避免把绝对路径、stack、Traceback 泄露到响应体（E2E 有回归用例）。
- Payload 收敛：对外只返回前端渲染所需字段（例如 `normalizeRunSummaries`、grid 的 `toGridIndexCellPayload`）；不要把原始解析对象全量透传。
- 缓存：图片 route 设置 `Cache-Control: public, max-age=86400`；其他 JSON route 不强行缓存。

## 反模式

- 不要在 route 里直接 `path.join(root, userInput)` 读取文件；必须先走 `lib/comfyui-path.ts` 的校验与 root-scope 解析。
- 不要把异常 message 原样返回（尤其包含本机路径/环境信息）。
- 不要把这些 route 迁到 Edge runtime（会破坏当前的实现假设）。
