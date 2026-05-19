<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-04-25 -->

# data/ — 输入资产（只读）

## 概览

- 这里存放可复现的输入资产：模型配置（YAML + API/Workflow JSON + 图片）、prompt YAML/CSV、以及静态页面 Markdown。默认都当"版本化资产"看待，不要在实现任务时随手改。

## 结构与用途

- `data/models/` 下各模型目录（如 `example/`、`test/`）
  - `config.yaml`：`runner_config.py` 读取的 run 配置，schema 固定为 `image-run-config/v1`
  - `api.json`：ComfyUI API JSON，供生图脚本直接读取
  - `workflow.json`：ComfyUI 工作流导出文件，用于保留可视化工作流版本
  - `image.*`：封面图源文件

- `data/prompts/X/common_prompts.*`
  - X 轴结构化 prompt 资产（YAML + CSV）；当前主链路直接消费 YAML

- `data/prompts/Y/300_NAI_Styles_Table*`
  - Y 轴 prompt 资产（YAML + CSV）；由 CSV 转换并经 Danbooru 标注而来，当前主链路直接消费 YAML
  - YAML 使用 `prompt-y-table/v3`，每个 `tags[]` 都有 `type: general | artists`；`info.type` 已移除

- `data/info-page.md` / `data/privacy-policy-page.md`
  - 静态页面 Markdown 源文件，供 `app/info/` 和 `app/privacy-policy/` 页面渲染

## 约定

- `data/models/*/config.yaml`、`data/prompts/**/*.yaml` 都是当前主链路会直接消费的资产；改 schema 前先检查 `runner_config.py`、`prompt_grid.py` 和测试契约。
- CSV 更像"源材料"，YAML 更像"已编译资产"；默认优先更新转换脚本，再决定是否重生成 YAML。

## 反模式

- 不要把运行输出（`run.json`/`metadata.jsonl`/图片）写进 `data/`；输出应在 `comfyui_api_outputs/` 或通过 `--run-dir` 指定
- 不要把模型配置目录当临时草稿；它们属于可执行配置，不是随手记事本
