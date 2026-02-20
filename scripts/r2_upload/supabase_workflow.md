# Supabase 初始化/创建/连接工作流

本指南说明如何在本地和远程使用 Supabase。

## 本工作流（Docker）

### 启动本地 Supabase

首先初始化本地开发环境：

```bash
# 1. 启动本地 Supabase（首次运行会拉取 Docker 镜像）
# 注意：本仓库可能没有全局安装 supabase CLI，使用 pnpm dlx 作为备用
supabase start
# 或
pnpm dlx supabase start
```

检查状态：

```bash
supabase status
# 或
pnpm dlx supabase status
```

输出示例：

```
API URL: http://localhost:54321
DB URL: postgresql://postgres:postgres@localhost:54322/postgres
Studio URL: http://localhost:54323
anon key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
service_role key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**重要：** 保存输出的 `API URL` 和 `service_role key`，用于环境变量配置。

### 重置数据库

如果需要清空数据库并重新应用迁移：

```bash
supabase db reset
# 或
pnpm dlx supabase db reset
```

### 停止本地 Supabase

```bash
supabase stop
# 或
pnpm dlx supabase stop
```

## 远程工作流（Supabase Cloud）

### 1. 创建 Supabase 项目

1. 访问 https://supabase.com/dashboard
2. 登录或注册账号
3. 点击 "New Project"
4. 填写项目信息：
   - 组织名称
   - 项目名称
   - 数据库密码（**务必保存**）
   - 区域（选择距离你最近的区域）
5. 等待项目创建完成（通常需要 1-2 分钟）

### 2. 获取连接凭证

在 Supabase Dashboard 中：

1. 进入你的项目
2. 点击左侧导航栏的 "Settings" → "API"
3. 复制以下信息：

   - **Project URL**（格式：`https://xxxxx.supabase.co`）→ 设置为环境变量 `SUPABASE_URL`
   - **service_role secret**（以 `eyJ` 开头的长字符串）→ 设置为环境变量 `SUPABASE_SERVICE_ROLE_KEY`

### 3. 可选：链接本地到远程

如果你想要将本地的迁移和类型定义同步到远程：

```bash
# 链接到远程项目（会交互式选择项目）
supabase link
# 或
pnpm dlx supabase link

# 推送本地迁移到远程
supabase db push
# 或
pnpm dlx supabase db push
```

### 4. 可选：从远程拉取结构

```bash
# 拉取远程数据库结构到本地
supabase db pull
# 或
pnpm dlx supabase db pull
```

## 环境变量配置

在 `.env` 文件中添加：

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## 安全警告

### ⓵ 不要提交密钥到版本控制

- `.env` 文件已在 `.gitignore` 中（请确保）
- **绝对不要** 将 `.env` 提交到 Git
- **绝对不要** 在代码中硬编码任何 Supabase 凭证
- **绝对不要** 在 PR、Issue 或文档中粘贴真实的密钥

### ⓶ 不要在日志中打印密钥

在代码中处理密钥时：

```python
# ❌ 错误：打印完整密钥
print(f"Service role key: {os.getenv('SUPABASE_SERVICE_ROLE_KEY')}")

# ✅ 正确：只打印长度或脱敏信息
key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
print(f"Service role key configured (length: {len(key) if key else 0})")

# ✅ 正确：或者打印脱敏版本
def mask_secret(secret: str) -> str:
    if not secret:
        return "MISSING"
    return f"{secret[:8]}...{secret[-8:]}"

print(f"Service role key: {mask_secret(key)}")
```

### ⓶ 使用 service_role key 的注意事项

- `service_role key` 有绕过 RLS（Row Level Security）的权限
- **仅用于服务器端代码**（如 Python 脚本、API 路由）
- **永远不要** 在客户端代码（如浏览器、React 组件）中使用 `service_role key`
- 客户端应使用 `anon key`（本指南未涉及，因为 R2 上传脚本在服务器端运行）

## 常见问题

### 问题：`supabase: command not found`

**解决：** 使用 `pnpm dlx supabase ...` 替代 `supabase ...`

### 问题：Docker 未运行

**解决：** 确保 Docker Desktop 或 Docker daemon 正在运行

### 问题：端口冲突（54321/54322/54323 已被占用）

**解决：**

1. 检查占用端口的进程：
   ```bash
   lsof -i :54321
   lsof -i :54322
   lsof -i :54323
   ```

2. 停止冲突进程，或在 `supabase/config.toml` 中修改端口配置

### 问题：远程连接失败

**检查：**

1. 环境变量是否正确设置
2. `SUPABASE_URL` 格式是否正确（应包含 `https://`）
3. `SUPABASE_SERVICE_ROLE_KEY` 是否完整复制（未被截断）
4. 项目是否已创建且处于 Active 状态

## 相关文件

- `supabase/migrations/`: 数据库迁移文件
- `supabase/seed.sql`: 种子数据
- `supabase/config.toml`: Supabase CLI 配置
- `scripts/r2_upload/`: 使用 Supabase 的上传脚本

## 参考资源

- Supabase 官方文档：https://supabase.com/docs
- Supabase CLI 文档：https://supabase.com/docs/guides/cli

## 最小工作流

本节提供最核心的命令集合，用于日常开发。

### 初始化（仅用于全新项目）

**注意：** 本仓库已包含 `supabase/` 目录和迁移文件，无需再次初始化。如果你从零开始新项目，请运行：

```bash
supabase init
# 或
pnpm dlx supabase init
```

### 启动和检查状态

```bash
# 启动本地 Supabase（首次运行会拉取 Docker 镜像）
supabase start
# 或
pnpm dlx supabase start

# 检查运行状态（获取 API URL、DB URL、Studio URL、密钥）
supabase status
# 或
pnpm dlx supabase status

# 停止本地 Supabase
supabase stop
# 或
pnpm dlx supabase stop
```

### 数据库管理

```bash
# 重置数据库（清空并重新应用所有迁移）
supabase db reset
# 或
pnpm dlx supabase db reset

# 创建新迁移
supabase migration new add_users_table
# 或
pnpm dlx supabase migration new add_users_table

# 推送本地迁移到远程（需先执行 supabase link）
supabase db push
# 或
pnpm dlx supabase db push

# 拉取远程数据库结构到本地
supabase db pull
# 或
pnpm dlx supabase db pull
```

### 类型生成

```bash
# 生成本地数据库的 TypeScript 类型定义（文档用）
supabase gen types --local > types/supabase.ts
# 或
pnpm dlx supabase gen types --local > types/supabase.ts
```

### 远程同步（可选）

```bash
# 链接本地项目到远程 Supabase 项目（会交互式选择项目）
supabase link
# 或
pnpm dlx supabase link
```

### ORM/tRPC 考量

当前项目规模下，ORM/tRPC 不必需。如后续扩展服务器端逻辑，可在以下情况考虑引入：

- ORM（如 Prisma、Drizzle）：当业务复杂度增加，需要类型安全的数据库抽象时
- tRPC：当前使用 Next.js API Routes；当需要端到端类型安全且前端与服务器共享类型时

### 命令降级说明

如果全局未安装 Supabase CLI，所有命令都可以通过 `pnpm dlx supabase` 降级运行，无需额外安装步骤。
