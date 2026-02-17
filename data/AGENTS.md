# data/ — 输入资产（只读）

## 概览

- 这里存放可复现的输入 CSV 与 ComfyUI workflow JSON；默认情况下把它们当作“资产”，不要在实现任务时随手改。

## 结构与用途

- `data/prompts/X/common_prompts.csv`
  - X 轴 prompt 表；列名通过 `scripts/prompt_grid.py` 的 `X_COLUMN_MAPPING` 映射成内部 key

- `data/prompts/Y/300_NAI_Styles_Table-test.csv`
  - Y 轴示例表；默认读取列名 `Artists`（见 `scripts/prompt_grid.py:read_y_rows()`）

- `data/comfyui-flow/*.json`
  - ComfyUI workflow 模板；默认使用 `data/comfyui-flow/CKNOOBRF.json`（见 `scripts/comfyui_part1_generate.py`）
  - workflow 需要包含 `KSampler`，并能追溯到 `CLIPTextEncode`（positive/negative）与 `EmptyLatentImage`

## 反模式

- 不要把运行输出（`run.json`/`metadata.jsonl`/图片）写进 `data/`；输出应在 `comfyui_api_outputs/` 或通过 `--run-dir` 指定
