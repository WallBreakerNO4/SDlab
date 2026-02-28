# app/api/comfyui/ — ComfyUI 数据查询 API（Node runtime）

## 概览

- App Router route handlers：主要从 Supabase 读取数据（runs/images/variants），本地文件读取作降级。不调用 Python。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| runs 列表 | `runs/route.ts` | Supabase 查询，返回最小化 summaries |
| run 详情 | `run/[runDir]/route.ts` | 校验 runDir；返回 `{ run, xLabels, yLabels }` |
| grid 索引 | `run/[runDir]/grid/route.ts` | cells 经 payload 收敛（适配虚拟网格） |
| row 级图片查询 | `run/[runDir]/row/route.ts` | 按行查询，支持分页/筛选 |
| 图片代理（本地降级） | `image/[runDir]/[...imagePath]/route.ts` | 路径安全链 + stream + cache-control |

## 约定（本目录特有）

- 运行时：每个 `route.ts` 必须保持 `export const runtime = "nodejs"`
- 数据源：优先 Supabase（`lib/supabase-server.ts`）；仅在 Supabase 不可用时降级到本地文件
- 校验顺序：runDir → `assertAllowedRunDir()`；图片额外 `assertSafeRelativeImagePath()` → `resolvePathUnderRoot()`
- 错误响应：404 仅用于"不存在/非法输入"；500 用固定短文案；不泄露绝对路径/stack/Traceback
- Payload 收敛：对外只返回前端渲染所需字段；不要把原始解析对象全量透传
- 缓存：图片 route 设置 `Cache-Control: public, max-age=86400`；JSON route 不强行缓存

## 反模式

- 不要在 route 里直接 `path.join(root, userInput)` 读取文件；必须先走 `lib/comfyui-path.ts` 校验
- 不要把异常 message 原样返回（尤其包含本机路径/环境信息）
- 不要把这些 route 迁到 Edge runtime
- 不要在 route 中直接 `createClient()`；使用 `lib/supabase-server.ts` 统一客户端
