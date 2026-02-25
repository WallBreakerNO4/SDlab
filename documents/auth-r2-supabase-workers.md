# 身份认证与 R2 分级存储实现说明

本文档详细说明了 SD-Style-Lab 项目中接入 Supabase Auth 与 Cloudflare R2 图片分级访问控制的架构设计、配置步骤及安全策略。

## 1. 架构概览

系统采用 Next.js (App Router) 作为前端和 API 中枢，通过 Supabase SSR 处理身份验证，并利用 Cloudflare R2 进行图片分级存储。

### 数据流图

```text
浏览器 (Browser)
    |
    |-- (1) 登录/Session 刷新 --> Next.js Middleware/Proxy --> Supabase Auth
    |
    |-- (2) 获取公开图片 ------> API (/api/media/public/*) --> R2 Public Bucket (或本地目录)
    |
    |-- (3) 获取私有图片 ------> API (/api/media/variant/*)
                                     |
                                     |-- 校验 Supabase Session
                                     |-- 查询 DB 确认权限 (RLS)
                                     |-- 从 R2 Private Bucket 读取流
```

## 2. 图片分级存储策略

图片根据安全性与访问频率分为三个类别（Category）和三层变体。

### 三类图片 Category
- **normal**: 公开内容，通过 `/api/media/public` 访问。
- **advance**: 私有内容，必须登录。
- **nsfw**: 私有内容，必须登录。

### 变体分层
- **L1 (Original/Display)**: 原始 PNG 或高质量展示图。
- **L2 (Thumbnail)**: 缩略图，用于网格预览。
- **Blurhash**: 低精度的占位颜色哈希，存储在数据库。

### 存储桶策略 (Cloudflare R2)

系统固定使用以下两个 Binding 名称与 R2 桶交互：

- **Public Bucket (`sdsl-public`)**: 绑定为 `SDSL_R2_PUBLIC`。仅存储 `normal` 类别的 `display` 与 `thumb` 变体。通过 `/api/media/public/*` 直接访问。
- **Private Bucket (`sdsl-private`)**: 绑定为 `SDSL_R2_PRIVATE`。存储 `advance` 与 `nsfw` 类别的所有变体。特别注意：**所有**类别的原始文件 (`original_png`) 均存储在此私有桶中。通过 `/api/media/variant/[variantId]` 鉴权后访问。

> 提示：Bucket 的真实名称在 `wrangler.jsonc` 中可配置，但代码中引用的 Binding 名称 (`SDSL_R2_PUBLIC`/`SDSL_R2_PRIVATE`) 是固定的。

## 3. 缓存策略

### 公开资源 (Public)
- **路径**: `/api/media/public/[...r2Key]`
- **Header**: `Cache-Control: public, max-age=31536000, immutable`
- **说明**: 永久缓存，利用 R2 自身的 ETag 校验。

### 私有资源 (Private)
- **路径**: `/api/media/variant/[variantId]`
- **Header**:
  - `Cache-Control: private, no-store, no-cache, must-revalidate`
  - `Vary: Cookie, Authorization`
  - `X-Content-Type-Options: nosniff`
- **说明**: 禁止 CDN 和浏览器缓存。`Vary` 头确保缓存按用户会话隔离。

## 4. 私有媒体代理接口

私有媒体通过 `variantId` 间接访问，不暴露真实 R2 Key。

### 关键参数
- **`variantId`**: 变体在数据库中的唯一 UUID。
- **`download=1`**: 添加 `Content-Disposition: attachment` 响应头，触发浏览器下载。

### 高级功能：Range 支持
代理接口完整支持 `Range` 请求头（断点续传/音视频流式播放）：
- 支持 `bytes=start-end`, `bytes=start-`, `bytes=-suffix` 格式。
- 正确处理 `206 Partial Content` 状态码。
- 返回 `Content-Range`, `Content-Length`, `Accept-Ranges` 响应头。

## 5. Supabase Auth 配置

项目使用 `@supabase/ssr` 实现跨 Server/Client 的身份管理。

### OAuth 配置步骤
1. **Redirect URLs**: 在 Supabase Dashboard 添加 `http://localhost:3000/auth/callback`（及生产环境域名）。
2. **Providers**: 启用 Google, GitHub, Microsoft, Apple 等。
3. **自动链接 (Identity Linking)**: 默认启用。当用户使用不同 Provider 但 Email 相同登录时，Supabase 会自动将其链接到同一个 User ID。

### 会话刷新 (Middleware)
在 `middleware.ts` 中通过 `updateSession` 调用 `supabase.auth.getClaims()`。注意不推荐在 Middleware 中使用 `getSession()`，因为它无法保证 JWT 签名的强制校验。

## 6. 环境配置清单

### 前端环境变量 (.env.local / .env.example)
这些变量在运行时被 Next.js 读取。前端公开变量必须以 `NEXT_PUBLIC_` 开头。

| 变量名 | 示例值 | 说明 |
| --- | --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://xxx.supabase.co` | Supabase 项目 API 地址 |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | `sb_pub_xxx` | Supabase 客户端匿名 Key |
| `NEXT_PUBLIC_R2_PUBLIC_BASE_URL` | `https://pub-xxx.r2.dev` | 公开资源的外部访问基地址 |

### Cloudflare Wrangler 绑定 (Bindings)
在 `wrangler.jsonc` 中配置，用于在 Cloudflare 运行时访问 R2 资源。这些不是环境变量，不能在 `.env` 中设置。

| Binding 名称 | 类型 | 对应存储桶名称 | 说明 |
| --- | --- | --- | --- |
| `SDSL_R2_PUBLIC` | `r2_bucket` | `sdsl-public` | 公开资源存储桶 |
| `SDSL_R2_PRIVATE` | `r2_bucket` | `sdsl-private` | 私有资源存储桶 |

### 本地开发可选变量 (仅开发环境)
用于在没有 R2 访问权限时通过本地文件系统模拟。

| 变量名 | 示例值 | 说明 |
| --- | --- | --- |
| `SDSL_LOCAL_R2_DIR` | `./.sisyphus/evidence/local-r2` | 模拟 R2 的本地根目录，包含 `public/` 和 `private/` 子目录 |

## 7. 本地开发与部署

### 本地开发 (Local Dev)
- **启动 Next.js**: `pnpm dev`
- **本地 Supabase**: `pnpm dlx supabase start` (需安装 Docker)
- **本地 R2 模拟**: 设置 `SDSL_LOCAL_R2_DIR` 指向本地目录，系统会自动从该目录的 `public/` 和 `private/` 子目录读取文件。

### 部署 (Cloudflare Workers)
- **预览**: `pnpm preview` (执行 OpenNext 构建并在本地 wrangler 预览)
- **部署**: `pnpm run deploy` (直接部署到 Cloudflare Workers)
- **类型生成**: `pnpm cf-typegen` (更新 `worker-configuration.d.ts`)

## 8. 新增依赖说明

- **@supabase/supabase-js**: Supabase 核心客户端 SDK。
- **@supabase/ssr**: 官方提供的 Next.js 服务端渲染集成方案。
- **blurhash**: 图片占位符哈希算法核心库。
- **react-blurhash**: 用于在 React 中渲染 Blurhash 占位图的组件。
- **@opennextjs/cloudflare**: 将 Next.js 转换为 Cloudflare Worker 运行格式的适配器。
- **wrangler**: Cloudflare 开发者命令行工具。
## 9. 常见故障排查

- **登录后仍显示 401**: 检查浏览器 Cookie 是否包含 `sb-xxx-auth-token`。确保 Middleware 能够正常执行。
- **私有图片 404**: 确认 `variantId` 在数据库中存在，且其关联的 `bucket` 字段为 `private`。
- **图片缓存不更新**: 公开图片使用了 `immutable` 缓存，更新内容需更换 R2 Key（通常带哈希）。
- **RLS 错误**: 私有图片访问依赖数据库 RLS 策略。如果数据库查询为空，即使 R2 有文件也会返回 404。
