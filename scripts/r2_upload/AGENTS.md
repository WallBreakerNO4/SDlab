<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-07-20 -->

# scripts/r2_upload/ — R2 上传 + Supabase 写入

## 概览

- 完整的图片上传管线：从本地 run 产物读取 → 多变体编码（webp/avif）→ R2 上传 → Supabase 索引写入；同目录也提供 run 数据删除工具。
- 术语约定：本目录生成的 `display_*` / `thumb_*` 变体统一称为“展示页缩略图”；run 级 `image.*` 属于封面图，`images/*` 属于主页缩略图集合。两类首页图片资产会随 run 级静态资源一起上传，Web 侧首页当前通过 `/api/comfyui/runs` 返回的 `assets.cover` / `assets.homepage_cards` 消费它们。

## 去哪儿改

| 任务                      | 位置                     | 备注                                                                                 |
| ------------------------- | ------------------------ | ------------------------------------------------------------------------------------ |
| 上传主入口与 CLI          | `upload_images_to_r2.py` | `build_parser()`；`-F/--force-publish`；编排编码/上传/写入；4 条 tqdm 进度条          |
| R2 存储客户端             | `r2_client.py`           | boto3 S3 兼容；`R2Client` + 重试 + 结构化错误（`R2ClientError` 含 retryable 标志）   |
| Supabase 批量写入         | `supabase_writer.py`     | `SupabaseWriter.upsert_upload_index()`；分批 upsert + 并发写入；含 `_build_run_style_item_rows()` 从 image payload 的 `y_style_key` upsert `run_style_items`（on_conflict=`run_id,style_key`） |
| 上传规划与变体            | `upload_planner.py`      | `_build_run_plan()`；多变体规划 + ThreadPoolExecutor 并发编码；把 `y_style_key` 写入 grid_items 字段并规划 `run_style_items` 行；含旧 Mixer run 的 Y prompt 拆分回填 |
| R2 key 生成与 bucket 映射 | `r2_keys.py`             | key 格式：`runs/{run_dir}/{variant}_{filename}`；normal→public, advance/nsfw→private |
| 图片编码参数              | `encoding_params.py`     | webp/avif 质量/尺寸参数；展示页缩略图中的 thumb 尺寸为 display 一半（向下取整，≥1）  |
| 变体图片处理              | `variants.py`            | PIL 缩放 + 编码；生成展示页缩略图所需的 display/thumb webp/avif                      |
| 上传合约类型              | `upload_contracts.py`    | `PlannedUpload`/`UploadResult` 等 dataclass                                          |
| 上传执行器                | `upload_executor.py`     | 并发上传调度                                                                         |
| 上传 I/O                  | `upload_io.py`           | 文件读写工具                                                                         |
| 上传发现                  | `upload_discovery.py`    | 从 metadata.jsonl 发现待上传图片                                                     |
| 上传运行时                | `upload_runtime.py`      | 运行时环境初始化                                                                     |
| manifest 生成             | `manifest.py`            | JSON manifest 构建（公开/私有）；row `items[]` 携带可选图片级 BlurHash                |
| run 级静态资产上传        | `upload_planner.py`      | 识别并规划封面图/主页缩略图资产的上传与 DB 字段                                      |
| 路径安全                  | `path_safety.py`         | R2 key 路径校验                                                                      |
| PostgREST HTTP            | `postgrest_http.py`      | Supabase PostgREST HTTP 客户端封装                                                   |
| Supabase 环境             | `supabase_env.py`        | 环境变量读取（URL/key）                                                              |
| Supabase 数据归一化       | `supabase_normalize.py`  | 行数据归一化为 PostgREST 格式                                                        |
| 清空 bucket 工具          | `clear_bucket.py`        | 交互式清空 R2 bucket                                                                 |
| 删除 run 数据            | `delete_run.py`             | 删除指定 run 的 Supabase 记录 + R2 对象;`--run-dir` / `--dry-run` / `--yes`;`python -m scripts.r2_upload.delete_run` |

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
supabase_writer.py → 批量 upsert 到 Supabase（runs + snapshots + projection tables）
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
- 普通上传允许首次发布与相同 `release_id` 的幂等恢复；不同 release 必须显式使用 `-F/--force-publish`，且仅支持单个 `--run-dir`
- 发布顺序固定为不可变资源 → Supabase 数据/`run_view_index` → 可变 `view/current.json`；强制发布不重复上传已存在的内容寻址图片
- 旧 Mixer metadata 缺少 `y_common_prompt` 时，上传规划会校验 run 快照中的 Y YAML SHA256，并按 Y prompt 身份在内存中严格回填；不会改写本地 `metadata.jsonl`
- Mixer bootstrap 以可选 `yPromptParts` 暴露 Artist/Common Prompt；继续保留 `yLabels` 兼容旧前端，view schema 保持 v2
- Style Favorites 上传链路：新 run 上传时从 image payload 的 `y_style_key` 提取并 upsert `run_style_items`（`run_id,style_key,y_index,label`）；老 run 缺该字段时静默跳过，不阻断上传，历史映射由 `scripts/other/backfill_run_style_items.py` 回填
- row manifest 在每个图片 `items[]` 上写入可选 `blurhash`，与该 item 的 thumb/display 描述一起发布；public、`auth_sfw`、`auth_nsfw` 仍先按 category 过滤，不能让 NSFW BlurHash 进入 SFW manifest。旧 release 没有该字段时由 Web 端兼容为 `null`。
- I/O 统一用 `pathlib.Path`；中间编码产物写入 `_r2_upload_intermediate/`

## 反模式

- 不要把真实凭证文件或密钥内容提交到仓库（包含 `.env*` 与任何私有配置）
- 不要把 bucket/key/endpoint 等敏感细节写入异常 message 或日志
- 不要把上传结果写回 `data/`；默认运行产物归 `outputs/`，或由 `--run-dir` 指向的显式目录
- 不要把 ComfyUI 的整段响应对象塞进错误 context
