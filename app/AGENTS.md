# app/ — Next.js 展示网站（App Router）

## 概览

- 展示网站主入口：页面在 `app/**/page.tsx`，数据通过 Supabase 读取、图片通过 R2 公开/私有链接获取。API routes 提供数据查询和 R2 私有图片代理。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| 首页 runs 列表 | `app/page.tsx` | 从 Supabase 拉取 |
| run 详情页 | `app/runs/[runDir]/page.tsx` | 并行拉取 run 详情 + grid |
| API：runs 列表 | `app/api/comfyui/runs/route.ts` | Supabase 查询 |
| API：run 详情 | `app/api/comfyui/run/[runDir]/route.ts` | 校验 runDir + Supabase |
| API：grid 索引 | `app/api/comfyui/run/[runDir]/grid/route.ts` | cells 适配虚拟网格 |
| API：row 级图片查询 | `app/api/comfyui/run/[runDir]/row/route.ts` | 按行查询图片数据 |
| API：R2 私有图片代理 | `app/api/r2/private/[...r2Key]/route.ts` | aws4fetch 签名转发；路径安全校验 |
| API：图片流（本地降级） | `app/api/comfyui/image/[runDir]/[...imagePath]/route.ts` | 本地文件流 + cache-control |
| API 约定细则 | `app/api/comfyui/AGENTS.md` | runtime/校验/payload/错误映射 |
| 全局布局与样式入口 | `app/layout.tsx`、`app/globals.css` | fonts + token CSS vars |

## 约定（本目录特有）

- App Router API 运行时固定为 Node：每个 `route.ts` 保持 `export const runtime = "nodejs"`
- 数据源：API routes 主要从 Supabase 读取数据；`lib/comfyui-fs.ts` 仅作本地开发降级
- R2 代理：`app/api/r2/private/` 使用 aws4fetch 签名；路径必须经 `lib/r2-url.ts` 校验
- 输入校验：`runDir` 必须先通过 `lib/comfyui-path.ts:assertAllowedRunDir`；图片路径必须先 `assertSafeRelativeImagePath`
- 错误响应：对 404/400/500 区分返回；避免泄露绝对路径、stack、Traceback
- 前端 fetch：页面侧倾向用 type guard 校验返回 payload，再进入渲染

## 反模式

- 不要在页面/route 里直接拼接文件系统路径或绕过 `lib/comfyui-path.ts`
- 不要在 API 错误响应里返回异常堆栈或本机路径信息
- 不要把 `.next/` 或 `types/*.d.ts` 当作可编辑源码
- 不要在 route 中直接创建 Supabase 客户端；使用 `lib/supabase-server.ts`
