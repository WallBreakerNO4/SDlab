# scripts/generation/ — 核心生图实现

## 概览

- 8 个 Python 文件：CLI runner、ComfyUI HTTP/WS 客户端、workflow patch、prompt grid、错误处理。是生图逻辑的“心脏”。

## 去哪儿改

| 任务 | 位置 | 备注 |
| --- | --- | --- |
| CLI 参数/环境变量/落盘 | `comfyui_part1_generate.py` | `build_parser()`/`run()`；写 `run.json` + `metadata.jsonl` |
| ComfyUI HTTP/WS/错误码 | `comfyui_client.py` | `ComfyUIClientError`（`code`+`context`） |
| workflow 注入/追溯 | `workflow_patch.py` | 追溯 KSampler 到 CLIPTextEncode/EmptyLatentImage |
| prompt 归一化/hash/seed | `prompt_grid.py` | 纯函数优先 |
| prompt 模板加载 | `prompt_loader.py` | X/Y JSON 读取与验证 |
| 文件系统工具 | `fs_utils.py` | 安全路径拼接、原子写入 |
| 结果打包/输出 | `output_packager.py` | metadata.jsonl 行格式、图片引用 |

## 核心流程

```
main() → build_parser() → run()
  ↓
load_workflow() → patch_workflow(prompt, seed)
  ↓
comfy_submit_prompt() → comfy_ws_wait_prompt_done()
  ↓
comfy_download_image_to_path() → write metadata.jsonl + run.json
```

## 约定（本目录特有）

- 允许在“直接运行脚本文件”场景下修正 `sys.path`：先处理路径，再导入本地模块，并用 `# noqa: E402` 标注
- pyright：用文件级 `# pyright:` 指令做最小必要的规则调整；局部忽略只在外部库类型不完整处使用
- 结构化错误：`context` 里不要放敏感信息/超大对象；必要时只存 key 列表/摘要
- I/O 统一用 `pathlib.Path`；产物写入后必须 `flush + fsync`

## 反模式

- 不要把 ComfyUI 的整段响应对象塞进异常 message/context（体积与可序列化都会踩坑）
- 不要在 tqdm 循环里 `print()`；用 `logging` 并保持与 tqdm 的输出兼容
- 不要把生成参数复制到 `scripts/cli/` 层；菜单层只做分发
