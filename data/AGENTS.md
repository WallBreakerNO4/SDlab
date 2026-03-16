# data/ — 输入资产（只读）

## 概览

- 这里存放可复现的输入资产：prompt YAML、runner 配置 YAML、ComfyUI workflow JSON，以及少量原始 CSV。默认都当“版本化资产”看待，不要在实现任务时随手改。

## 结构与用途

- `data/runs/example.yaml` / `data/runs/test.yaml`
  - `runner_config.py` 读取的 run 配置；schema 固定为 `image-run-config/v1`
  - 负责绑定 `model` / `prompts` / `workflow` / `generation` / `selection` 五段配置

- `data/prompts/X/common_prompts.yaml`
  - X 轴结构化 prompt 资产；当前主链路直接消费 YAML

- `data/prompts/Y/300_NAI_Styles_Table*.yaml`
  - Y 轴 prompt 资产；由 CSV 转换而来，当前主链路直接消费 YAML

- `data/prompts/**/*.csv`
  - 原始输入表；仅供 `scripts/other/convert_*.py` 重新生成 YAML 时使用

- `data/comfyui-flow/api-json/*.json`
  - 供生图脚本直接读取的 ComfyUI API JSON；默认使用 `data/comfyui-flow/api-json/CKNOOBRF.json`（见 `scripts/generation/comfyui_part1_generate.py`）
  - workflow 需要包含 `KSampler`，并能追溯到 `CLIPTextEncode`（positive/negative）与 `EmptyLatentImage`

- `data/comfyui-flow/workflow-json/*.json`
  - ComfyUI 工作流导出文件；用于保留可视化工作流版本，不直接作为当前生图脚本的默认输入

## 约定

- `data/runs/*.yaml`、`data/prompts/**/*.yaml` 都是当前主链路会直接消费的资产；改 schema 前先检查 `runner_config.py`、`prompt_grid.py` 和测试契约。
- CSV 更像“源材料”，YAML 更像“已编译资产”；默认优先更新转换脚本，再决定是否重生成 YAML。

## 反模式

- 不要把运行输出（`run.json`/`metadata.jsonl`/图片）写进 `data/`；输出应在 `comfyui_api_outputs/` 或通过 `--run-dir` 指定
- 不要把 `data/runs/*.yaml` 当临时草稿；它们属于可执行配置，不是随手记事本
