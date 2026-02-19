# scripts/ — 核心实现

## 概览

- 这里是主“代码域”：CLI runner、ComfyUI HTTP/WS 客户端、workflow patch、prompt grid（顶层 `main.py` 只做委托）。

## 去哪儿改

| 任务 | 位置 | 备注 |
| --- | --- | --- |
| CLI 参数/环境变量/落盘合约 | `scripts/comfyui_part1_generate.py` | `build_parser()`/`run()`；写 `run.json` + `metadata.jsonl` |
| ComfyUI 请求/WS/错误码 | `scripts/comfyui_client.py` | `ComfyUIClientError`（`code`+`context`） |
| workflow JSON 注入 | `scripts/workflow_patch.py` | 追溯 `KSampler` 引用到 `CLIPTextEncode`/`EmptyLatentImage` |
| CSV 读取与 prompt/seed | `scripts/prompt_grid.py` | prompt 归一化 + sha256 hash + seed 派生 |
| 对外导出（给测试/调用） | `scripts/__init__.py` | `__all__` 统一导出 |

## Code Map（高频入口）

- `scripts/comfyui_part1_generate.py`
  - CLI：`build_parser()`、`main(argv)`；参数默认优先读 `COMFYUI_*` 环境变量
  - 主流程：`run(args)`；网格迭代 + 断点续跑（读取历史 `metadata.jsonl` 决定 skip）
  - 落盘：`run.json`（pretty JSON，`ensure_ascii=False`）+ `metadata.jsonl`（逐行 JSON，写入后 `flush + fsync`）
  - 并发：`ThreadPoolExecutor` 分提交/下载两个池；`tqdm` + `logging_redirect_tqdm`

- `scripts/comfyui_client.py`
  - HTTP：`comfy_submit_prompt()`、`comfy_get_history_item()`、`comfy_download_image_to_path()`
  - WS：`comfy_ws_connect()`、`comfy_ws_wait_prompt_done()`
  - 错误：`ComfyUIClientError` 及子类；错误信息短，细节进 `context`（必须可序列化）

- `scripts/workflow_patch.py`
  - `load_workflow()`：读 JSON → `WorkflowDict`
  - `patch_workflow()`：选择 `KSampler` → 追溯 `positive/negative/latent_image` 引用并写入 overrides

- `scripts/prompt_grid.py`
  - 读 JSON：`read_x_rows()`/`read_y_rows()`（从 `data/prompts/**.json` 读取）
  - prompt：`normalize_prompt()`/`compute_prompt_hash()`/`derive_seed()`

## 约定（本目录特有）

- 允许在“直接运行脚本文件”场景下修正 `sys.path`：先处理路径，再导入本地模块，并用 `# noqa: E402` 标注（见 `scripts/comfyui_part1_generate.py`）
- pyright：用文件级 `# pyright:` 指令做最小必要的规则调整；局部忽略只在外部库类型不完整处使用
- 结构化错误：`context` 里不要放敏感信息/超大对象；必要时只存 key 列表/摘要（测试对 message/内容有约束）

## 反模式

- 不要把 ComfyUI 的整段响应对象塞进异常 message/context（体积与可序列化都会踩坑）
- 不要在 tqdm 循环里 `print()`；用 `logging` 并保持与 tqdm 的输出兼容
