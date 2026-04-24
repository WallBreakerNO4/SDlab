<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-04-25 -->

# supabase/ — Supabase 本地开发配置与迁移

## 概览

- Supabase 项目配置、数据库迁移文件、种子数据。用于本地开发环境和远程 Supabase 项目同步；`.temp/` / `.branches/` 是 CLI 生成状态，不是源码。

## 去哪儿看

| 场景                  | 位置                                                          | 备注                                               |
| --------------------- | ------------------------------------------------------------- | -------------------------------------------------- |
| Supabase 项目配置     | `config.toml`                                                 | 端口/Auth/Storage 等本地开发配置                   |
| 数据库迁移            | `migrations/`                                                 | 时间戳命名的 SQL 迁移文件                          |
| ComfyUI schema 初始化 | `migrations/20260311075715_init_comfyui_schema_and_views.sql` | 早期 schema 起点；最终态以最新 projection 迁移为准 |
| 种子数据              | `seed.sql`                                                    | 本地开发用的测试数据                               |
| CLI 临时状态          | `.temp/`、`.branches/`                                        | `supabase` CLI 生成；不要当源码修改                |

## 约定（本目录特有）

- 本目录所有 Supabase CLI 命令统一直接使用 `supabase ...`。
- 迁移文件用 `supabase migration new <name>` 生成；不要手动创建/重命名迁移文件
- 迁移必须幂等：用 `CREATE TABLE IF NOT EXISTS`、`DO $$ ... $$` 等模式
- RLS 策略：所有表默认启用 RLS；新表必须附带明确的 policy
- 不要在迁移文件中硬编码凭证或环境特定值
- 本地重置：`supabase db reset` 会依次执行所有 migrations + seed.sql

## 反模式

- 不要直接修改已提交的迁移文件内容（如需修改则新建迁移）
- 不要在迁移中使用 `DROP TABLE` 等破坏性操作，除非有明确的数据迁移计划
- 不要把 `.temp/` 目录下的内容提交到版本控制
- 不要混用 `supabase ...`、`pnpm dlx supabase ...` 与 `npx supabase ...`；本仓库以直接执行 `supabase` 为准
