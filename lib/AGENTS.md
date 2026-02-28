# lib/ — Node 侧数据层（Supabase + R2 + ComfyUI 产物 + 路径安全）

## 概览

- Node 侧数据边界层：Supabase 客户端、R2 URL 构建、ComfyUI 产物解析、路径安全校验。供 `app/api/` routes 和页面使用。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| Supabase 服务端客户端 | `supabase-server.ts` | service role 客户端；`server-only` 导入守卫 |
| Supabase 类型定义 | `supabase-types.ts` | `SupabaseRunRow`/`SupabaseImageRow`/`SupabaseImageVariantRow`/`ImageCategory`/`R2Bucket` |
| R2 URL 构建与变体校验 | `r2-url.ts` | `publicObjectUrl()`/`privateObjectUrl()`；变体白名单校验 |
| run 目录发现与 run.json 解析 | `comfyui-fs.ts` | `discoverRunDirs()`/`loadRunDetail()`（本地降级用） |
| metadata.jsonl 解析与 grid 构建 | `comfyui-fs.ts` | `parseMetadataJsonl()`/`buildGridIndex()` |
| runDir/imagePath 安全校验 | `comfyui-path.ts` | allowlist + traversal 防护 |
| 领域类型与类型守卫 | `comfyui-types.ts` | `RunDir`/`GridCell`/`isValidRunDir` |
| className 合并工具 | `utils.ts` | `cn()`（`clsx` + `tailwind-merge`） |

## 约定（本目录特有）

- Supabase 客户端仅在 `supabase-server.ts` 初始化；其他文件不直接创建客户端实例
- `supabase-server.ts` 使用 `server-only` 包守卫，防止客户端 bundle 意外引入
- R2 URL 构建必须经过 `r2-url.ts` 的变体白名单校验；不要在 route/组件中自行拼接 R2 URL
- `runDir` 必须先过 `assertAllowedRunDir()`；图片路径必须先过 `assertSafeRelativeImagePath()`
- `metadata.jsonl` 按逐行 JSON 容错解析：坏行跳过，不阻断 grid 构建
- 对外 payload 倾向最小必要字段；避免直接透传原始文件内容

## 反模式

- 不要在 route 或组件层绕过本目录函数直接拼接磁盘路径或 R2 URL
- 不要放宽 `runDir` 正则或 imagePath 校验规则来"临时兼容"
- 不要把包含绝对路径/环境细节的底层错误原样透传给 API 响应
- 不要在客户端组件中导入 `supabase-server.ts`（`server-only` 会阻止，但也不要尝试绕过）
