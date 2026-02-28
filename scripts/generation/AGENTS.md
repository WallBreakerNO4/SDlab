# scripts/generation/ — 核心生图实现

## 概览

- 17 个 Python 文件：CLI runner（已拆分为 coordinator + 6 个 runner_* 模块）、ComfyUI HTTP/WS 客户端、workflow patch、prompt grid、重试、输出打包。是生图逻辑的"心脏"。

## 去哪儿改

| 任务 | 位置 | 备注 |
| --- | --- | --- |
| CLI 参数/环境变量/落盘 | `comfyui_part1_generate.py` | `build_parser()`/`run()`；写 `run.json` + `metadata.jsonl` |
| 并发协调（提交+下载） | `runner_coordinator.py` | `ThreadPoolExecutor` 双池 + tqdm 进度 |
| 运行环境初始化 | `runner_env.py` | 目录创建、环境变量读取、日志配置 |
| prompt 选择与跳过 | `runner_selection.py` | 断点续跑（读 `metadata.jsonl` 决定 skip） |
| payload 构造与提交 | `runner_payload.py` | workflow patch + submit prompt |
| 运行记录写入 | `runner_records.py` | `run.json` + `metadata.jsonl` 落盘（flush+fsync） |
| 重试策略与调度 | `runner_retry.py` | 错误分类 + 重试决策 |
| prompt 模板渲染 | `runner_prompt_template.py` | X/Y prompt 组合与模板注入 |
| workflow 上下文 | `runner_workflow_context.py` | workflow 加载与 KSampler 追溯缓存 |
| ComfyUI HTTP/WS/错误码 | `comfyui_client.py` | `ComfyUIClientError`（`code`+`context`） |
| workflow 注入/追溯 | `workflow_patch.py` | 追溯 KSampler → CLIPTextEncode/EmptyLatentImage |
| prompt 归一化/hash/seed | `prompt_grid.py` | 纯函数优先 |
| 结果打包/输出 | `output_packager.py` | metadata.jsonl 行格式、图片引用 |
| 重试失败项筛选 | `retry_failed_selection.py` | 从 metadata.jsonl 筛选 failed 项 |
| 重试执行 | `retry.py` | 重试入口与流程控制 |
| 运行回放 | `run_replay.py` | 从已有 metadata 重放运行 |

## 模块拆分结构

```
comfyui_part1_generate.py（入口）
  ↓
runner_env.py → 环境初始化
runner_selection.py → prompt 选择/skip
runner_workflow_context.py → workflow 加载/缓存
runner_prompt_template.py → prompt 模板渲染
runner_payload.py → payload 构造 + 提交
runner_records.py → 结果落盘
runner_retry.py → 重试策略
runner_coordinator.py → 并发调度（组合以上模块）
  ↓
output_packager.py → 最终打包
```

## 约定（本目录特有）

- 允许在"直接运行脚本文件"场景下修正 `sys.path`：先处理路径，再导入本地模块，并用 `# noqa: E402` 标注
- pyright：用文件级 `# pyright:` 指令做最小必要的规则调整；局部忽略只在外部库类型不完整处使用
- 结构化错误：`context` 里不要放敏感信息/超大对象；必要时只存 key 列表/摘要
- I/O 统一用 `pathlib.Path`；产物写入后必须 `flush + fsync`
- runner_* 模块间通过参数传递状态，不使用全局变量

## 反模式

- 不要把 ComfyUI 的整段响应对象塞进异常 message/context（体积与可序列化都会踩坑）
- 不要在 tqdm 循环里 `print()`；用 `logging` 并保持与 tqdm 的输出兼容
- 不要把生成参数复制到 `scripts/cli/` 层；菜单层只做分发
- 不要把 runner_* 模块合并回 `comfyui_part1_generate.py`；拆分是为了可测试性
