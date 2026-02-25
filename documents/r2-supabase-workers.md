# R2 + Supabase + Cloudflare Workers 部署与开发指南

本文档介绍项目的云端集成架构，包括 R2 存储、Supabase 数据库以及如何部署到 Cloudflare 平台。

## 1. 架构概览

项目采用“动静分离”与“私有保护”相结合的架构：

```text
[浏览器 (Client)]
    |
    |-- (Public URL) --> [Cloudflare R2 (sdslab-public)] : 公开变体 (WebP/AVIF)
    |
    |-- (API Request) -> [Cloudflare Workers / OpenNext] : Next.js 站点
                                |
                                |-- (Query) --> [Supabase (PostgreSQL)] : 元数据 (runs/images)
                                |
                                |-- (Proxy) --> [Cloudflare R2 (sdslab-private)] : 私有变体 (Original/NSFW)
```

### 核心组件说明
- **Supabase**: 存储所有运行（runs）、图片（images）及其变体（image_variants）的元数据。
- **R2 Public Bucket**: 存放公开访问的低分辨率预览图和普通分类图片。
- **R2 Private Bucket**: 存放原图、高敏感分类图片，不提供直链。
- **Next.js API**: 负责处理业务逻辑、权限校验，并为私有桶提供流式代理服务。

## 2. 环境变量清单

本地开发和云端部署均需配置以下变量（参考 `.env.example`）：

### Supabase 配置
- `SUPABASE_URL`: Supabase 项目 URL（例如 `https://xxx.supabase.co`）
- `SUPABASE_SERVICE_ROLE_KEY`: **仅限后端** 使用的具有绕过 RLS 权限的密钥

### R2 存储配置
- `R2_ENDPOINT`: R2 S3 API 端点（格式：`https://<ACCOUNT_ID>.r2.cloudflarestorage.com`）
- `R2_ACCESS_KEY_ID`: R2 API 令牌 Access Key
- `R2_SECRET_ACCESS_KEY`: R2 API 令牌 Secret Key
- `R2_PUBLIC_BUCKET`: 公开桶名（默认 `sdslab-public`）
- `R2_PRIVATE_BUCKET`: 私有桶名（默认 `sdslab-private`）
- `R2_PUBLIC_BASE_URL`: 公开桶的访问基址（自定义域名或 r2.dev）

## 3. 本地开发步骤

### 网站开发
1. 安装依赖：`pnpm install`
2. 配置 `.env`: 参考 `.env.example` 填写真实凭证
3. 启动开发服务器：`pnpm dev`
4. 访问：`http://localhost:3000`

### Supabase 集成
本地开发可以使用 Docker 版本的 Supabase 或直接连接远程项目。
- 详情参考：`scripts/r2_upload/supabase_workflow.md`
- 运行 `pnpm dlx supabase start` 启动本地环境。

### 私有代理验证
私有图片通过 `/api/r2/private/...` 接口访问。验证步骤如下：
1. 确保已在 `sdslab-private` 桶中手动上传一个测试文件 `test.png`。
2. 使用 curl 验证代理接口（假设已配置好环境变量）：
   ```bash
   # 示例：通过本地 API 获取私有桶图片
   curl -I http://localhost:3000/api/r2/private/test.png
   ```
   **预期结果**: 返回 `HTTP/1.1 200 OK`，且 `Content-Type` 正确。

## 4. 部署到 Cloudflare

推荐使用 **OpenNext** 路线将 Next.js 应用部署到 Cloudflare Pages。

### 部署步骤
1. **安装 OpenNext**:
   使用官方推荐的适配器（如 `@opennextjs/cloudflare`）。
2. **配置 `wrangler.toml`**:
   确保包含以下关键配置：
   ```toml
   compatibility_flags = ["nodejs_compat"]

   [vars]
   # 在此处或 Dashboard 设置非敏感环境变量

   # R2 绑定（可选，推荐 API 直接使用 S3 SDK 保持本地一致性）
   # [[r2_buckets]]
   # binding = "PRIVATE_BUCKET"
   # bucket_name = "sdslab-private"
   ```
3. **设置 Secrets**:
   通过命令行设置敏感密钥：
   ```bash
   wrangler pages secret put SUPABASE_SERVICE_ROLE_KEY
   wrangler pages secret put R2_SECRET_ACCESS_KEY
   ```
4. **构建与发布**:
   ```bash
   pnpm build:worker # 假设配置了 OpenNext 构建脚本
   wrangler pages deploy .open-next/assets
   ```

### 部署注意点
- **Public Bucket**: 建议在 Cloudflare R2 Dashboard 为 `sdslab-public` 绑定自定义域名（如 `images.yourdomain.com`），以获得更好的 CDN 性能。
- **Private 代理**: 站点代码中使用 `R2_PRIVATE_BUCKET` 环境变量。部署后，Workers 会自动处理代理请求。

## 5. 安全与未来扩展

### 代理策略
当前架构中，网站不使用 Next.js Middleware 做图片代理，而是通过专门的 API Route (`/api/r2/private/*`) 进行流式转发，以避免边缘运行时的内存限制和冷启动延迟。

### 登录接入替换点
若未来需要接入用户系统，可在以下位置进行修改：
- **权限校验**: 在 `/api/r2/private/*` 的路由处理逻辑中检查 Supabase Auth 会话。
- **RLS 策略**: 在 Supabase 中启用 Row Level Security (RLS)，并将 `SUPABASE_SERVICE_ROLE_KEY` 替换为受限的 `anon` 或用户的 `auth` token。

## 6. 参考资料
- `scripts/r2_upload/r2_provisioning.md`: 桶创建与域名绑定。
- `scripts/r2_upload/supabase_workflow.md`: 数据库迁移与本地开发。
