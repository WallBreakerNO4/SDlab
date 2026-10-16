<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-10-16 -->

# supabase/ — Supabase 本地开发配置与迁移

## 概览

- Supabase 项目配置与数据库迁移文件。用于本地开发环境和远程 Supabase 项目同步；`.temp/` / `.branches/` 是 CLI 生成状态，不是源码。
- 本地数据库开发环境（「本地开发阶段」）通过官方 seed.sql 流程复现生产数据：`supabase/seed.sql`（git 忽略，生产库导出的真实数据副本）+ `db reset`（迁移 + 种子一起重放）；网站经 `pnpm dev:local` 连本地库，普通 `pnpm dev` 保持连远端、行为零变化。架构决策见父工单 issue #17（Implementation Decisions），领域术语见根 `CONTEXT.md`。

## 去哪儿看

| 场景                  | 位置                                                          | 备注                                               |
| --------------------- | ------------------------------------------------------------- | -------------------------------------------------- |
| Supabase 项目配置     | `config.toml`                                                 | 端口/Auth/Storage 等本地开发配置                   |
| 数据库迁移            | `migrations/`                                                 | 时间戳命名的 SQL 迁移文件                          |
| ComfyUI schema 初始化 | `migrations/20260311075715_init_comfyui_schema_and_views.sql` | 初始 schema 与视图；后续变更以新迁移为准 |
| Style Favorites 表与 RLS | `migrations/20260717202836_add_style_favorites.sql`         | 两表、字段约束/基础索引、RLS policies 与角色 grants |
| 首页评测状态列        | `migrations/20260915095701_add_run_list_items_status_and_published_at.sql` | `run_list_items` 新增 `status` / `generated_cells` / `published_at`；历史行回填为已完结 / `total_cells` / `created_at`，并建 `published_at desc` 索引 |
| 模型对比查询索引      | `migrations/20260720120000_add_style_comparison_indexes.sql` | 收藏 keyset 分页索引 + style/run placement 覆盖索引 |
| 模型对比 RPC           | `migrations/20260720130000_add_style_comparison_rpcs.sql` | authenticated slice 聚合 + 公共模型目录聚合；均为 `SECURITY INVOKER` |
| 对比目录评测状态        | `migrations/20260920102643_add_style_comparison_models_status.sql` | 目录 RPC 返回 `status` 与 `published_at`，排序按 `published_at` 回退 `created_at`；重建函数后重新声明原 grants |
| 对比 BlurHash RPC      | `migrations/20260720140000_add_style_comparison_slice_blurhash.sql` | 三参数 slice RPC；materialized 有界集合关联 `run_grid_items`，按 NSFW 偏好返回紧凑 BlurHash tuple |
| RPC 性能验收           | `tests/style_comparison_rpc_explain.sql` | 用真实 viewer fixture 验证 1×1、1×6、40×12，并校验最大 slice 的 40/480/12 及 SFW/NSFW BlurHash 数量 |
| 本地开发命令手册       | 本文件「本地数据库开发手册」一节                     | 起栈/导出种子/重置/dev:local/GitHub dev OAuth/回填全流程 |
| CLI 临时状态          | `.temp/`、`.branches/`                                        | `supabase` CLI 生成；不要当源码修改                |

## 约定（本目录特有）

- 本目录所有 Supabase CLI 命令统一使用 `pnpm dlx supabase ...`。
- 迁移文件用 `pnpm dlx supabase migration new <name>` 生成；不要手动创建/重命名迁移文件
- 迁移必须幂等：用 `CREATE TABLE IF NOT EXISTS`、`DO $$ ... $$` 等模式
- RLS 策略：所有表默认启用 RLS；新表必须附带明确的 policy
- 模型对比依赖 `(user_id, created_at desc, style_key)` 收藏分页索引和 `(style_key, run_dir) include (y_index)` placement 索引；新增查询形态时用新迁移调整，不改已提交迁移。
- `get_style_comparison_slice` 只授予 `authenticated`，必须保持 `SECURITY INVOKER`、显式 `(select auth.uid())`、函数内 40 style / 12 run 上限和固定异常文案；不得接受客户端 `user_id` 参数。overload 形式同时提供两参数与三参数版本：三参数版本通过 `p_include_nsfw` 控制 `run_grid_items.category`，requested/owned/target placement CTE 必须 `MATERIALIZED`，BlurHash tuple 按 `x_index, batch_index` 稳定排序。清理旧版本函数需另开迁移。
- BlurHash 数据读取 `run_grid_items.blurhash` 字段。
- `get_style_comparison_models` 只授予 `anon, authenticated`，一次 JOIN 已发布视图、列表投影和 run X columns，返回 `status` 与 `published_at`（排序按 `published_at` 回退 `created_at`）；它只服务共享 5 分钟缓存，不得混入用户收藏或 grant。
- 新函数默认执行权限必须显式从 `PUBLIC`（以及受限角色）撤销后再按最小角色集合 `GRANT`；不要依赖 PostgreSQL 的默认函数权限。
- 不要在迁移文件中硬编码凭证或环境特定值
- 本地重置：`pnpm dlx supabase db reset` 以已提交的 migrations + seed.sql 重建数据库；seed.sql 含生产数据副本，永不进 git
- env 文件按消费者划分（详见根 `.env.example` 说明段）：`.env.local-db` 只放 Web/Python 的本地数据库连接变量；本地栈自身消费的 GitHub dev OAuth 凭据放根 `.env`（`config.toml` 的 `env()` 只读根 `.env`）。

## 反模式

- 不要直接修改已提交的迁移文件内容（如需修改则新建迁移）
- 不要在迁移中使用 `DROP TABLE` 等破坏性操作，除非有明确的数据迁移计划
- 不要把 `.temp/` 目录下的内容提交到版本控制
- 不要用不存在的 style/run 键做性能验收；EXPLAIN 必须使用真实共同覆盖 40×12 的 fixture，并检查返回计数。
- 本仓库统一使用 `pnpm dlx supabase ...` 运行 Supabase 命令，不要混用其他方式
- 不要把 `supabase/seed.sql`、`.env.local-db` 或任何真实数据/凭据提交进 git；不要把 `.env.local-db` 改名为 `.env.local`（会被普通 dev 自动加载，破坏「pnpm dev = 远端」铁律）
- 不要在 `pnpm dev`（无 `:local` 后缀）下验证本地数据库行为；本地库验证一律走 `pnpm dev:local`

## 本地数据库开发手册

完整流程：**起栈 → 导出种子 → 重置 → dev:local → 登录 → 回填**。所有命令在仓库根目录执行。

### 1. 起栈与重置（迁移 + 种子一起重放）

```bash
pnpm dlx supabase start        # 首次或 stop 后起栈
pnpm dlx supabase db reset     # 重放全部迁移 + 导入 seed.sql；搞砸后的万能撤回
```

`db reset` 会清空包括 auth schema 在内的整个数据库，因此**每次 reset 后本地登录身份都会变化**，需要重走第 4 步回填。

### 2. 导出生产数据种子（手动低频，需要刷新数据副本时重跑）

```bash
pnpm dlx supabase db dump --data-only -f supabase/seed.sql \
  -x "auth.users,auth.sessions,auth.refresh_tokens,auth.identities,auth.flow_state,auth.mfa_amr_claims,auth.mfa_factors,auth.mfa_challenges,auth.mfa_recovery_code_sets,auth.mfa_recovery_codes,auth.one_time_tokens,auth.audit_log_entries"
```

- 从 linked 远端项目导出（首次会引导 `supabase login` + `supabase link`）；约 140MB，不进 git。
- **`-x` 排除清单不可省**：当前 CLI 版本的 `--data-only` 会把 auth schema 也 dump 下来（users/sessions/refresh_tokens 等真实生产会话数据）。混进种子会导致本地栈出现「幽灵登录」——浏览器里残留的生产会话 cookie 命中种子副本后被本地 GoTrue 直接换发新会话，看似登录成功实则从未走本地 OAuth，且违背「auth schema 留空」设计。
- dump 使用 replica 会话模式落地，排除 auth 后 public 侧指向 `auth.users` 的悬空 user_id 不影响导入（FK 在 `session_replication_role = replica` 下跳过校验，RLS 使悬空行不可见）。
- 只做幂等覆盖：想完全重建就先 `db reset` 再导入。

### 3. 用本地库启动网站

```bash
pnpm dev:local    # dotenv-cli 注入 .env.local-db 后跑 next dev
```

- `.env.local-db` 只放本地数据库连接变量（URL / service role key / publishable key 及镜像），值从 `pnpm dlx supabase status -o env` 抄；文件缺失时创建它（参考根 `.env.example` 说明段）。
- 其余机密（R2 凭据等）由根 `.env` 补漏：进程 env 优先于 Next 自动加载的 `.env`。
- 普通 `pnpm dev` 不加载 `.env.local-db`（非 Next 标准名），保持连远端库、行为零变化。

### 4. GitHub dev OAuth App（一次性注册）

本地栈登录走 GitHub OAuth，须单独注册一个 dev OAuth App（与生产 App 分开——一个 OAuth App 只有一个 callback URL）：

1. 打开 https://github.com/settings/developers → **New OAuth App**；
2. Homepage URL 填 `http://localhost:3000`，Authorization callback URL 填 `http://localhost:54321/auth/v1/callback`（GitHub 官方允许 localhost http 回调）；3. 把 Client ID / Client Secret 写进**根 `.env`**：

   ```bash
   SUPABASE_AUTH_EXTERNAL_GITHUB_CLIENT_ID=<client id>
   SUPABASE_AUTH_EXTERNAL_GITHUB_SECRET=<client secret>
   ```

   注意必须放根 `.env`——`config.toml` 的 `env()` 只读项目根目录的 `.env`，且 `supabase start` 没有 `--env-file` flag；
4. `pnpm dlx supabase stop --no-backup && pnpm dlx supabase start` 让凭据生效。

> callback URL 三处必须**精确一致**（GitHub 要求逐字匹配，`127.0.0.1` ≠ `localhost`）：GitHub App 注册值、`config.toml` 的 `redirect_uri`（已显式设置为 `http://localhost:54321/auth/v1/callback`，不设时 GoTrue 默认用 `127.0.0.1` 会导致 GitHub 弹警告页）、以及本手册的指引值。若历史上注册过 `127.0.0.1` 形态的 callback，可在 GitHub App 设置页改掉。

本地只配 GitHub；Google / Azure 在 `config.toml` 中 `enabled = false`，不要为本地栈重新启用。

### 5. 本地登录身份回填（每次 db reset 后重跑）

`db reset` 清空 auth schema，重放种子后用户表的 `user_id` 悬空；用本地 GitHub OAuth 登录一次产生**本地登录身份**，再把它回填为数据归属：

1. `pnpm dev:local` 启动网站，浏览器打开 `http://localhost:3000`，用 GitHub 登录一次；
2. 查出新身份的 id：

   ```bash
   docker exec supabase_db_images-script psql -U postgres -d postgres -tAc \
     "select id, email from auth.users order by created_at desc limit 5;"
   ```

3. 把下面 SQL 中的 `<LOCAL_USER_ID>` 替换为该 id 后，在本地库执行（幂等，可重复跑）。

   语义说明：回填是**叠加归属**——把种子副本里悬空的偏好/收藏行**复制**到本地登录身份名下；悬空原行保留不删（RLS 使其只对原 user_id 可见，对本地登录无副作用），下次 `db reset` 随种子重放自然消除。不要用 `DELETE` 清悬空行：那会连生产数据副本里其他真实用户的行一起删掉，破坏「真实数据量」的验证意义。

   ```sql
   -- 回填 NSFW 偏好归属：本地身份尚无偏好行时，取一份生产悬空偏好行复制过来
   insert into public.user_preferences (user_id, show_nsfw)
   select '<LOCAL_USER_ID>', show_nsfw
   from public.user_preferences
   where user_id <> '<LOCAL_USER_ID>'
   order by updated_at desc
   limit 1
   on conflict (user_id) do nothing;

   -- 回填画师串收藏归属：把全部生产悬空收藏行复制到本地登录身份名下
   insert into public.user_style_favorites (user_id, style_key, label, created_at)
   select '<LOCAL_USER_ID>', style_key, label, created_at
   from public.user_style_favorites
   where user_id <> '<LOCAL_USER_ID>'
   on conflict (user_id, style_key) do nothing;
   ```

   执行方式：`docker exec supabase_db_images-script psql -U postgres -d postgres -c "<SQL>"`，或粘贴进 Studio（`http://127.0.0.1:54323`）的 SQL Editor。
4. 刷新页面确认收藏 / 对比 / 法典入口在真实数据量下可见。

> 这是手册化的手工流程，不做成脚本：回填只在本地开发时使用，频率为每次 `db reset` 后一次。SQL 首次执行约 `INSERT 0 1`（偏好）+ `INSERT 0 19`（收藏，行数随种子浮动），重复执行两次均 `INSERT 0 0` 即幂等生效。
