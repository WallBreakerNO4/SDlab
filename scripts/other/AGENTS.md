# scripts/other/ — 离线资产转换工具

## 概览

- 本目录放轻量离线脚本：把 prompt CSV 转成 YAML 资产，供 `data/` 与生图脚本消费；文件名历史上保留了 `json`，但当前实际输出是 YAML。

## 去哪儿看

| 场景             | 位置                       | 备注                                                     |
| ---------------- | -------------------------- | -------------------------------------------------------- |
| X 轴 CSV 转 YAML | `convert_x_csv_to_json.py` | 读取多列 tag + 中英描述，写 `schema/items`               |
| Y 轴 CSV 转 YAML | `convert_y_csv_to_json.py` | 解析加权 tags，支持多文件批量转换                        |
| 共用导出         | `__init__.py`              | 对外暴露 `convert_*_csv_to_yaml` / `parse_weighted_tags` |
| 输入资产约定     | `data/AGENTS.md`           | 输出默认与 CSV 同目录                                    |

## 约定（本目录特有）

- 输入/输出统一用 `pathlib.Path`；默认把 YAML 写在源 CSV 旁边，必要时通过 `--out` / `--out-dir` 覆盖。
- `convert_x_csv_to_json.py` 依赖 `convert_y_csv_to_json.py:parse_weighted_tags()`；共用的 tag 解析逻辑不要复制两份。
- 允许像其他直接运行脚本一样修正 `sys.path`，以支持 `python scripts/other/...py` 调用。
- 这里处理的是可复现资产转换，不读 Web/API/Supabase/R2 运行时状态。
- 输出 payload 形态固定为 `schema + items`；改字段前先检查 `data/` 资产与 `scripts/generation/prompt_grid.py` 消费方。

## 反模式

- 不要把转换输出写进 `comfyui_api_outputs/` 或运行目录。
- 不要在这里引入生图、上传、认证或数据库逻辑。
- 不要被文件名误导去改成 JSON；仓库当前资产格式以 YAML 为准。
