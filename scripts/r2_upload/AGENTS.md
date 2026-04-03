# scripts/r2_upload/ — R2 上传 + Supabase 写入

## 概览

- 完整的图片上传管线：从本地 run 产物读取 → 多变体编码（webp/avif）→ R2 上传 → Supabase 索引写入。19 个 Python 文件。
- 术语约定：本目录生成的 `display_*` / `thumb_*` 变体统一称为“展示页缩略图”；run 级 `image.*` 属于封面图，`images/*` 属于主页缩略图集合。两类首页图片资产会随 run 级静态资源一起上传，Web 侧首页当前通过 `/api/comfyui/runs` 返回的 `assets.cover` / `assets.homepage_cards` 消费它们。

## 去哪儿改

| 任务                      | 位置                     | 备注                                                                                 |
| ------------------------- | ------------------------ | ------------------------------------------------------------------------------------ |
| 上传主入口与 CLI          | `upload_images_to_r2.py` | `build_parser()`；编排编码/上传/写入；4 条 tqdm 进度条                               |
| R2 存储客户端             | `r2_client.py`           | boto3 S3 兼容；`R2Client` + 重试 + 结构化错误（`R2ClientError` 含 retryable 标志）   |
| Supabase 批量写入         | `supabase_writer.py`     | `SupabaseWriter.upsert_upload_index()`；分批 upsert + 并发写入                       |
| 上传规划与变体            | `upload_planner.py`      | `_build_run_plan()`；多变体规划 + ThreadPoolExecutor 并发编码                        |
| R2 key 生成与 bucket 映射 | `r2_keys.py`             | key 格式：`runs/{run_dir}/{variant}_{filename}`；normal→public, advance/nsfw→private |
| 图片编码参数              | `encoding_params.py`     | webp/avif 质量/尺寸参数；展示页缩略图中的 thumb 尺寸为 display 一半（向下取整，≥1）  |
| 变体图片处理              | `variants.py`            | PIL 缩放 + 编码；生成展示页缩略图所需的 display/thumb webp/avif                      |
| 上传合约类型              | `upload_contracts.py`    | `PlannedUpload`/`UploadResult` 等 dataclass                                          |
| 上传执行器                | `upload_executor.py`     | 并发上传调度                                                                         |
| 上传 I/O                  | `upload_io.py`           | 文件读写工具                                                                         |
| 上传发现                  | `upload_discovery.py`    | 从 metadata.jsonl 发现待上传图片                                                     |
| 上传运行时                | `upload_runtime.py`      | 运行时环境初始化                                                                     |
| manifest 生成             | `manifest.py`            | JSON manifest 构建（公开/私有）                                                      |
| run 级静态资产上传        | `upload_planner.py`      | 识别并规划封面图/主页缩略图资产的上传与 DB 字段                                      |
| 路径安全                  | `path_safety.py`         | R2 key 路径校验                                                                      |
| PostgREST HTTP            | `postgrest_http.py`      | Supabase PostgREST HTTP 客户端封装                                                   |
| Supabase 环境             | `supabase_env.py`        | 环境变量读取（URL/key）                                                              |
| Supabase 数据归一化       | `supabase_normalize.py`  | 行数据归一化为 PostgREST 格式                                                        |
| 清空 bucket 工具          | `clear_bucket.py`        | 交互式清空 R2 bucket                                                                 |

## 核心流程

```
upload_images_to_r2.py (CLI)
  ↓
upload_discovery.py → 发现 metadata.jsonl 中的图片
  ↓
upload_planner.py → 规划展示页缩略图变体（display_webp/avif + thumb_webp/avif）
  ↓ (ThreadPoolExecutor 并发编码)
variants.py + encoding_params.py → 生成变体文件
  ↓
r2_keys.py → 生成 R2 key + 确定 bucket（public/private）
  ↓
upload_executor.py + r2_client.py → 并发上传到 R2
  ↓
supabase_writer.py → 批量 upsert 到 Supabase（runs + images + variants）
```

## 错误处理体系

- `R2ClientError`（含 `retryable` 标志）：子类 `R2AuthError`/`R2RateLimitError` 等
- `SupabaseWriterError`（含 `category`: config/argument/remote）：提取 PostgREST 错误码
- 所有错误类 `context` 字段必须可 JSON 序列化；敏感信息用 hash12() 脱敏

## 约定（本目录特有）

- 上传逻辑与生图逻辑分层：不要反向耦合到 `scripts/generation/` 内部流程
- 凭证输入优先走环境变量（`R2_*`/`SUPABASE_*`），不在仓库内落盘明文配置
- 变体命名：`display_webp`/`display_avif`/`thumb_webp`/`thumb_avif`，文档中统称“展示页缩略图”
- `run/image.*` 与同级 `images/*` 这类 run 级静态资源现在已进入上传与 Supabase 写入链路；但它们在 Web 侧仍应作为独立的封面图/主页缩略图字段建模，不要与展示页缩略图混用。
- bucket 分配：normal category → public bucket；advance/nsfw → private bucket
- 上传支持可配置并发（`--upload-workers`）和 dry-run 模式
- I/O 统一用 `pathlib.Path`；中间编码产物写入 `_r2_upload_intermediate/`

## 反模式

- 不要把真实凭证文件或密钥内容提交到仓库（包含 `.env*` 与任何私有配置）
- 不要把 bucket/key/endpoint 等敏感细节写入异常 message 或日志
- 不要把上传结果写回 `data/`；运行产物仍归 `comfyui_api_outputs/`
- 不要把 ComfyUI 的整段响应对象塞进错误 context
