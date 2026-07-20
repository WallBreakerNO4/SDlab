<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-07-20 -->

# scripts/other/ — 离线资产转换工具

## 概览

- 本目录放轻量离线脚本：把 prompt CSV 转成 YAML 资产，供 `data/` 与生图脚本消费；文件名历史上保留了 `json`，但当前实际输出是 YAML。
- 例外：`backfill_run_style_items.py` 是已落地的一次性回填脚本，会读 Supabase `runs` 并幂等 upsert `run_style_items`；除此之外本目录仍不引入数据库逻辑。

## 去哪儿看

| 场景             | 位置                       | 备注                                                     |
| ---------------- | -------------------------- | -------------------------------------------------------- |
| X 轴 CSV 转 YAML | `convert_x_csv_to_json.py` | 读取多列 tag + 中英描述，写 `schema/items`               |
| Y 轴 CSV 转 YAML | `convert_y_csv_to_json.py` | 解析加权 tags，输出 v3 `tags[].type`，支持多文件批量转换  |
| Y tag 类型标注   | `annotate_y_tag_types_from_danbooru.py` | 从 Danbooru `/tags.json` 标注 `general` / `artists` |
| 历史 run 回填    | `backfill_run_style_items.py`           | 按 run.json 记录的 sha256 确定性重放 Y 资产，幂等 upsert `run_style_items` |
| 共用导出         | `__init__.py`              | 对外暴露 `convert_*_csv_to_yaml` / `parse_weighted_tags` |
| 输入资产约定     | `data/AGENTS.md`           | 输出默认与 CSV 同目录                                    |

## 约定（本目录特有）

- 输入/输出统一用 `pathlib.Path`；默认把 YAML 写在源 CSV 旁边，必要时通过 `--out` / `--out-dir` 覆盖。
- `convert_x_csv_to_json.py` 依赖 `convert_y_csv_to_json.py:parse_weighted_tags()`；共用的 tag 解析逻辑不要复制两份。
- 允许像其他直接运行脚本一样修正 `sys.path`，以支持 `python scripts/other/...py` 调用。
- 这里处理的是可复现资产转换，不读 Web/API/Supabase/R2 运行时状态。
- 输出 payload 形态固定为 `schema + items`；Y 轴 prompt 当前使用 `prompt-y-table/v3`，tag 类型写在 `tags[].type`，不再写 `info.type`。

## 反模式

- 不要把转换输出写进 `outputs/` 或其他运行目录。
- 不要在这里引入生图、上传、认证或数据库逻辑（唯一例外是 spec 批准的 `backfill_run_style_items.py` 一次性回填）。
- 不要被文件名误导去改成 JSON；仓库当前资产格式以 YAML 为准。
