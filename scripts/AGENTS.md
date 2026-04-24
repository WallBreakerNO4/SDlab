<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-04-25 -->

# scripts/ — 核心实现（生图 + R2 上传）

## 概览

- 主"代码域"：生图 runner（generation/）、R2 上传（r2_upload/）、交互菜单（cli/）、辅助转换（other/）。顶层 `main.py` 只做委托。

## 去哪儿改

| 任务                       | 位置                                                       | 备注                                          |
| -------------------------- | ---------------------------------------------------------- | --------------------------------------------- |
| CLI 参数/环境变量/落盘合约 | `scripts/generation/comfyui_part1_generate.py`             | 入口；fresh-run 主链路走 `--config`           |
| run 配置解析               | `scripts/generation/runner_config.py`                      | 校验 `data/runs/*.yaml` 与 repo-relative 资产 |
| 并发协调                   | `scripts/generation/runner_coordinator.py`                 | ThreadPoolExecutor 双池                       |
| ComfyUI 请求/WS/错误码     | `scripts/generation/comfyui_client.py`                     | `ComfyUIClientError`（`code`+`context`）      |
| workflow JSON 注入         | `scripts/generation/workflow_patch.py`                     | 追溯 KSampler 引用链                          |
| prompt 组合/hash/seed      | `scripts/generation/prompt_grid.py`                        | 纯函数优先                                    |
| 重试失败项                 | `scripts/generation/retry_failed_selection.py`、`retry.py` | 筛选 + 重跑                                   |
| 菜单交互与入口注册         | `scripts/cli/menu.py`、`scripts/cli/registry.py`           | 交互菜单、入口动态加载                        |
| CSV / prompt 资产转换      | `scripts/other/convert_*.py`                               | 文件名遗留 `json`，实际输出 YAML              |
| R2 上传主入口              | `scripts/r2_upload/upload_images_to_r2.py`                 | 编码变体 + 并发上传 + Supabase 写入           |
| R2 客户端                  | `scripts/r2_upload/r2_client.py`                           | boto3 S3 兼容 + 重试                          |
| Supabase 批量写入          | `scripts/r2_upload/supabase_writer.py`                     | PostgREST upsert + 分批                       |
| 对外导出                   | `scripts/__init__.py`                                      | `__all__` 统一导出                            |

## 子目录职责（避免串层）

- `scripts/generation/`：核心 runner（已拆分 15+ 模块）+ ComfyUI 通信 + workflow patch + metadata 落盘
- `scripts/cli/`：仅处理"如何选择并执行脚本"；不持有生图/上传业务状态
- `scripts/other/`：离线资产转换工具；规则见 `scripts/other/AGENTS.md`
- `scripts/r2_upload/`：R2 上传 + Supabase 写入（19 个 Python 文件）；不把凭证细节扩散到其他目录

- 当前 fresh-run 主链路：`main.py` / 菜单 → `comfyui_part1_generate.py --config ...` → `runner_config.py` → runner\_\* 模块

## 约定（本目录特有）

- 允许在"直接运行脚本文件"场景下修正 `sys.path`（`# noqa: E402`）
- pyright：用文件级 `# pyright:` 指令做最小必要的规则调整
- 结构化错误：`context` 里不要放敏感信息/超大对象（测试对 message/内容有约束）

## 反模式

- 不要把 ComfyUI 的整段响应对象塞进异常 message/context
- 不要在 tqdm 循环里 `print()`；用 `logging`
- 不要在 `scripts/cli/` 里复制 `scripts/generation/` 或 `scripts/r2_upload/` 的业务参数解析
