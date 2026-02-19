# lib/ — ComfyUI 产物读取与路径安全

## 概览

- `lib/` 是 Node 侧数据边界：从 `comfyui_api_outputs/` 读取 `run.json`/`metadata.jsonl`，并提供路径安全校验给 `app/api/comfyui/**/route.ts`。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| run 目录发现与 run.json 解析 | `lib/comfyui-fs.ts` | `discoverRunDirs()`、`loadRunDetail()` |
| metadata.jsonl 解析与 grid 构建 | `lib/comfyui-fs.ts` | `parseMetadataJsonl()`、`buildGridIndex()` |
| runDir/imagePath 安全校验 | `lib/comfyui-path.ts` | allowlist + traversal 防护 |
| 领域类型与类型守卫 | `lib/comfyui-types.ts` | `RunDir`、`GridCell`、`isValidRunDir` |

## 约定（本目录特有）

- 读取层只做“解析 + 归一化 + 安全校验”，不耦合 UI 展示逻辑。
- `runDir` 必须先过 `assertAllowedRunDir(...)`；图片路径必须先过 `assertSafeRelativeImagePath(...)`，再 `resolvePathUnderRoot(...)`。
- `metadata.jsonl` 按“逐行 JSON”容错解析：坏行跳过，不阻断整个 grid 构建。
- 对外 payload 倾向最小必要字段（上层 route 再做收敛），避免直接透传原始文件内容。

## 反模式

- 不要在 route 或组件层绕过本目录函数直接拼接磁盘路径。
- 不要放宽 `runDir` 正则或 imagePath 校验规则来“临时兼容”输入。
- 不要把包含绝对路径/环境细节的底层错误原样透传给 API 响应。
