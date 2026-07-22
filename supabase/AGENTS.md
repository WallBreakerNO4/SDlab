<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-07-20 -->

# supabase/ — Supabase 本地开发配置与迁移

## 概览

- Supabase 项目配置与数据库迁移文件。用于本地开发环境和远程 Supabase 项目同步；`.temp/` / `.branches/` 是 CLI 生成状态，不是源码。

## 去哪儿看

| 场景                  | 位置                                                          | 备注                                               |
| --------------------- | ------------------------------------------------------------- | -------------------------------------------------- |
| Supabase 项目配置     | `config.toml`                                                 | 端口/Auth/Storage 等本地开发配置                   |
| 数据库迁移            | `migrations/`                                                 | 时间戳命名的 SQL 迁移文件                          |
| ComfyUI schema 初始化 | `migrations/20260311075715_init_comfyui_schema_and_views.sql` | 早期 schema 起点；最终态以最新 projection 迁移为准 |
| Style Favorites 表与 RLS | `migrations/20260717202836_add_style_favorites.sql`         | 两表、字段约束/基础索引、RLS policies 与角色 grants |
| 模型对比查询索引      | `migrations/20260720120000_add_style_comparison_indexes.sql` | 收藏 keyset 分页索引 + style/run placement 覆盖索引 |
| 模型对比 RPC           | `migrations/20260720130000_add_style_comparison_rpcs.sql` | authenticated slice 聚合 + 公共模型目录聚合；均为 `SECURITY INVOKER` |
| 对比 BlurHash RPC      | `migrations/20260720140000_add_style_comparison_slice_blurhash.sql` | 三参数 slice RPC；materialized 有界集合关联 `run_grid_items`，按 NSFW 偏好返回紧凑 BlurHash tuple |
| RPC 性能验收           | `tests/style_comparison_rpc_explain.sql` | 用真实 viewer fixture 验证 1×1、1×6、40×12，并校验最大 slice 的 40/480/12 及 SFW/NSFW BlurHash 数量 |
| CLI 临时状态          | `.temp/`、`.branches/`                                        | `supabase` CLI 生成；不要当源码修改                |

## 约定（本目录特有）

- 本目录所有 Supabase CLI 命令统一使用 `pnpm dlx supabase ...`。
- 迁移文件用 `pnpm dlx supabase migration new <name>` 生成；不要手动创建/重命名迁移文件
- 迁移必须幂等：用 `CREATE TABLE IF NOT EXISTS`、`DO $$ ... $$` 等模式
- RLS 策略：所有表默认启用 RLS；新表必须附带明确的 policy
- 模型对比依赖 `(user_id, created_at desc, style_key)` 收藏分页索引和 `(style_key, run_dir) include (y_index)` placement 索引；新增查询形态时用新迁移调整，不改已提交迁移。
- `get_style_comparison_slice` 只授予 `authenticated`，必须保持 `SECURITY INVOKER`、显式 `(select auth.uid())`、函数内 40 style / 12 run 上限和固定异常文案；不得接受客户端 `user_id` 参数。三参数版本通过 `p_include_nsfw` 控制 `run_grid_items.category`，requested/owned/target placement CTE 必须 `MATERIALIZED`，BlurHash tuple 按 `x_index, batch_index` 稳定排序。
- 历史 BlurHash 直接读取已有 `run_grid_items.blurhash`；部署三参数 RPC 不需要数据库回填、R2 改写或依赖本地 `outputs/`。
- 三参数 RPC 以 overload 形式新增，当前保留已提交的两参数版本，避免 migration 先于 Worker 部署时旧实例调用失败；稳定发布后的旧函数清理必须另开迁移。
- `get_style_comparison_models` 只授予 `anon, authenticated`，一次 JOIN 已发布视图、列表投影和 run X columns；它只服务共享 5 分钟缓存，不得混入用户收藏或 grant。
- 新函数默认执行权限必须显式从 `PUBLIC`（以及受限角色）撤销后再按最小角色集合 `GRANT`；不要依赖 PostgreSQL 的默认函数权限。
- 不要在迁移文件中硬编码凭证或环境特定值
- 本地重置：`pnpm dlx supabase db reset` 以已提交的 migrations 重建数据库；当前不跟踪 seed 数据文件

## 反模式

- 不要直接修改已提交的迁移文件内容（如需修改则新建迁移）
- 不要在迁移中使用 `DROP TABLE` 等破坏性操作，除非有明确的数据迁移计划
- 不要把 `.temp/` 目录下的内容提交到版本控制
- 不要用不存在的 style/run 键做性能验收；EXPLAIN 必须使用真实共同覆盖 40×12 的 fixture，并检查返回计数，避免把空结果计划误判为满载性能。
- 本仓库统一使用 `pnpm dlx supabase ...` 运行 Supabase 命令，不要混用其他方式
