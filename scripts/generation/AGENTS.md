<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-04-25 -->

# scripts/generation/ — 核心生图实现

## 概览

- 本目录是生图逻辑的“心脏”：CLI runner、`runner_config.py`、多个 `runner_*` 模块、ComfyUI HTTP/WS 客户端、workflow patch、prompt grid、重试、输出打包都在这里。
- run 级静态资产识别也从这里起步：`runner_config.py` 会把 run 目录下的 `image.*` 识别为封面图、`images/*` 识别为主页缩略图源资产，并把这些元信息写进后续产物供上传链路消费。

## 去哪儿改

| 任务                    | 位置                         | 备注                                                  |
| ----------------------- | ---------------------------- | ----------------------------------------------------- |
| CLI 参数/运行模式/落盘  | `comfyui_part1_generate.py`  | `build_parser()`/`run()`；fresh-run 入口接 `--config` |
| 运行配置 schema / 校验  | `runner_config.py`           | `load_runner_config()`；校验 `data/runs/*.yaml`       |
| 并发协调（提交+下载）   | `runner_coordinator.py`      | `ThreadPoolExecutor` 双池 + tqdm 进度                 |
| 运行环境初始化          | `runner_env.py`              | 目录创建、环境变量读取、日志配置                      |
| prompt 选择与跳过       | `runner_selection.py`        | 断点续跑（读 `metadata.jsonl` 决定 skip）             |
| payload 构造与提交      | `runner_payload.py`          | workflow patch + submit prompt                        |
| 运行记录写入            | `runner_records.py`          | `run.json` + `metadata.jsonl` 落盘（flush+fsync）     |
| 重试策略与调度          | `runner_retry.py`            | 错误分类 + 重试决策                                   |
| prompt 模板渲染         | `runner_prompt_template.py`  | X/Y prompt 组合与模板注入                             |
| workflow 上下文         | `runner_workflow_context.py` | workflow 加载与 KSampler 追溯缓存                     |
| ComfyUI HTTP/WS/错误码  | `comfyui_client.py`          | `ComfyUIClientError`（`code`+`context`）              |
| workflow 注入/追溯      | `workflow_patch.py`          | 追溯 KSampler → CLIPTextEncode/EmptyLatentImage       |
| prompt 归一化/hash/seed | `prompt_grid.py`             | 纯函数优先                                            |
| 结果打包/输出           | `output_packager.py`         | metadata.jsonl 行格式、图片引用                       |
| run 级静态资产识别      | `runner_config.py`           | 识别封面图 `image.*` 与主页缩略图目录 `images/*`      |
| 重试失败项筛选          | `retry_failed_selection.py`  | 从 metadata.jsonl 筛选 failed 项                      |
| 重试执行                | `retry.py`                   | 重试入口与流程控制                                    |
| 运行回放                | `run_replay.py`              | 从已有 metadata 重放运行                              |

## 模块拆分结构

```
comfyui_part1_generate.py（入口）
  ↓
runner_config.py → 解析 `--config` / 绑定 prompts/workflow/model
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
- fresh-run 默认通过 `--config` 驱动；prompt/workflow/model 元数据从 `RunnerConfig` 进入后续模块，不再靠零散 CLI 旗标拼装
- `RunnerConfig` 除 prompts/workflow/model 外，也负责携带 run 级封面图/主页缩略图资产元信息；这些资产由上传链路继续写入 R2 + Supabase，而不是由 Web 直接读本地目录
- runner\_\* 模块间通过参数传递状态，不使用全局变量

## 反模式

- 不要把 ComfyUI 的整段响应对象塞进异常 message/context（体积与可序列化都会踩坑）
- 不要在 tqdm 循环里 `print()`；用 `logging` 并保持与 tqdm 的输出兼容
- 不要把生成参数复制到 `scripts/cli/` 层；菜单层只做分发
- 不要把 runner\_\* 模块合并回 `comfyui_part1_generate.py`；拆分是为了可测试性
