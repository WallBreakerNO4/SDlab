# app/ — Next.js 展示网站（App Router）

## 概览

- 这里是展示网站的主入口：页面在 `app/**/page.tsx`，数据通过 `app/api/comfyui/**/route.ts` 读取 `comfyui_api_outputs/`。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| 首页 runs 列表 | `app/page.tsx` | 拉取 `/api/comfyui/runs` |
| run 详情页 | `app/runs/[runDir]/page.tsx` | 并行拉取 run 详情 + grid |
| API：runs 列表 | `app/api/comfyui/runs/route.ts` | 返回 run summaries |
| API：run 详情 | `app/api/comfyui/run/[runDir]/route.ts` | 返回 run + x/y labels |
| API：grid 索引 | `app/api/comfyui/run/[runDir]/grid/route.ts` | 返回 cells（适配前端渲染） |
| API：图片流 | `app/api/comfyui/image/[runDir]/[...imagePath]/route.ts` | `Cache-Control` + content-type |
| 全局布局与样式入口 | `app/layout.tsx`、`app/globals.css` | fonts + token CSS vars |

## 约定（本目录特有）

- App Router API 运行时固定为 Node：每个 `route.ts` 都应保持 `export const runtime = "nodejs"`
- 输入校验：`runDir` 必须先通过 `lib/comfyui-path.ts:assertAllowedRunDir`（allowlist 来自 `discoverRunDirs()`）；图片路径必须先 `assertSafeRelativeImagePath`
- 错误响应：对 404/400/500 区分返回；避免泄露绝对路径、stack、Traceback（E2E 有安全回归用例）
- 前端 fetch：页面侧倾向用 type guard 校验返回 payload，再进入渲染（例如 `app/runs/[runDir]/page.tsx`）

## 反模式

- 不要在页面/route 里直接拼接文件系统路径或绕过 `lib/comfyui-path.ts`
- 不要在 API 错误响应里返回异常堆栈或本机路径信息
- 不要把 `.next/` 或 `types/*.d.ts` 当作可编辑源码
