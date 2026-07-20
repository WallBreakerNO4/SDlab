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
| CLI 临时状态          | `.temp/`、`.branches/`                                        | `supabase` CLI 生成；不要当源码修改                |

## 约定（本目录特有）

- 本目录所有 Supabase CLI 命令统一使用 `pnpm dlx supabase ...`。
- 迁移文件用 `pnpm dlx supabase migration new <name>` 生成；不要手动创建/重命名迁移文件
- 迁移必须幂等：用 `CREATE TABLE IF NOT EXISTS`、`DO $$ ... $$` 等模式
- RLS 策略：所有表默认启用 RLS；新表必须附带明确的 policy
- 模型对比依赖 `(user_id, created_at desc, style_key)` 收藏分页索引和 `(style_key, run_dir) include (y_index)` placement 索引；新增查询形态时用新迁移调整，不改已提交迁移。
- 不要在迁移文件中硬编码凭证或环境特定值
- 本地重置：`pnpm dlx supabase db reset` 以已提交的 migrations 重建数据库；当前不跟踪 seed 数据文件

## 反模式

- 不要直接修改已提交的迁移文件内容（如需修改则新建迁移）
- 不要在迁移中使用 `DROP TABLE` 等破坏性操作，除非有明确的数据迁移计划
- 不要把 `.temp/` 目录下的内容提交到版本控制
- 本仓库统一使用 `pnpm dlx supabase ...` 运行 Supabase 命令，不要混用其他方式
