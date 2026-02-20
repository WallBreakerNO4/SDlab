# R2 桶创建与访问策略

本文档说明如何创建 Cloudflare R2 桶并配置公开访问策略。

## 桶划分

本项目使用两个 R2 桶：

- **`sdslab-public`**: 公开桶
  - 仅承载 `category='normal'` 的 `display_*`/`thumb_*` 变体
  - 通过自定义域名或 `r2.dev` 提供公开访问
  - 使用强缓存策略：`Cache-Control: public,max-age=31536000,immutable`

- **`sdslab-private`**: 私有桶
  - 承载所有 `original_png` 变体
  - 承载 `category='advance'` 和 `category='nsfw'` 的所有变体
  - 不绑定公开域名
  - 未来由 Cloudflare Worker 代理或使用 presigned URL 访问

## 使用 wrangler 创建桶

### 1. 安装并登录 wrangler

```bash
# 安装 wrangler（如果尚未安装）
npm install -g wrangler

# 登录 Cloudflare 账号
wrangler login

# 查看当前账号信息（获取 account_id）
wrangler whoami
```

### 2. 创建桶

```bash
# 创建公开桶
wrangler r2 bucket create sdslab-public

# 创建私有桶
wrangler r2 bucket create sdslab-private
```

### 3. 验证桶创建成功

```bash
# 列出所有 R2 桶
wrangler r2 bucket list
```

预期输出应包含 `sdslab-public` 和 `sdslab-private`。

## 配置公开访问（Dashboard 操作）

### 路径 1：绑定自定义域名（生产环境推荐）

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. 进入 **R2** → **Buckets**
3. 点击 `sdslab-public` 桶
4. 点击 **Settings** → **Public Access**
5. 点击 **Connect a domain**
6. 选择你的域名（例如 `images.yourdomain.com`）
7. 保存并等待 DNS 生效

### 路径 2：启用 r2.dev（仅用于开发环境）

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. 进入 **R2** → **Buckets**
3. 点击 `sdslab-public` 桶
4. 点击 **Settings** → **Public Access**
5. 启用 r2.dev 子域名访问
6. 保存后获得公开 URL（例如 `https://sdslab-public.<account-id>.r2.cloudflarestorage.com`）

**注意**：`r2.dev` 仅用于开发，不应用于生产环境。

## S3 兼容上传配置

上传脚本使用 boto3（S3 兼容 API）连接 R2。需配置以下环境变量。

### 环境变量清单

将以下变量添加到 `.env` 文件（**不要提交到 Git**）：

```bash
# R2 S3 API 端点（必需）
# 格式：https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_ENDPOINT=https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com

# R2 S3 访问密钥（必需）
# 在 Cloudflare Dashboard 创建 R2 API Token
R2_ACCESS_KEY_ID=YOUR_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY=YOUR_SECRET_ACCESS_KEY

# R2 桶名（必需）
R2_PUBLIC_BUCKET=sdslab-public
R2_PRIVATE_BUCKET=sdslab-private

# 公开桶的公开访问基础 URL（可选，用于生成直链）
# 如果绑定了自定义域名，填写完整域名（例如 https://images.yourdomain.com）
# 如果使用 r2.dev，填写 r2.dev URL
R2_PUBLIC_BASE_URL=https://YOUR_PUBLIC_BASE_URL
```

### 创建 R2 API Token

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. 进入 **R2** → **Manage R2 API Tokens**
3. 点击 **Create API Token**
4. 配置权限：
   - **Account**: `Your Account`
   - **Permissions**: `Admin R2 Object Read & Write`
5. 复制生成的 **Access Key ID** 和 **Secret Access Key**
6. 将密钥填入 `.env` 文件

**警告**：R2 API Token 只在创建时显示一次，丢失需重新创建。

## 缓存策略

- **公开桶**：对象 key 设计为不可变（包含 content hash 或版本号）
  - 缓存头：`Cache-Control: public,max-age=31536000,immutable`
  - 上传脚本会为所有公开桶对象设置此头部

- **私有桶**：不依赖长缓存
  - 缓存头：`Cache-Control: private, max-age=0, no-cache`
  - 未来通过 Worker 动态控制缓存

## Uploader 桶使用约定

上传脚本从环境变量读取桶名，**不在代码中硬编码**：

- `R2_PUBLIC_BUCKET`: 公开桶名（默认 `sdslab-public`）
- `R2_PRIVATE_BUCKET`: 私有桶名（默认 `sdslab-private`）
- `R2_ENDPOINT`: S3 API 端点
- `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`: 认证凭据

**重要**：日志和异常消息**不包含**真实 bucket 名、endpoint 或密钥。

## 安全提示

- **不要提交 `.env` 文件到 Git**：包含真实密钥，已加入 `.gitignore`
- **Dashboard 管理公开访问**：wrangler 不支持绑定域名，需在 Dashboard 操作
- **私有桶无公开访问**：不绑定自定义域名，也不启用 r2.dev

## 验证清单

- [ ] 两个桶创建成功：`sdslab-public`、`sdslab-private`
- [ ] 公开桶已配置公开访问（自定义域名或 r2.dev）
- [ ] `.env` 文件包含所有必需变量（`R2_ENDPOINT`、`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY`、`R2_PUBLIC_BUCKET`、`R2_PRIVATE_BUCKET`）
- [ ] R2 API Token 具有正确的 R2 读写权限
- [ ] 运行 `python -m scripts.r2_upload.upload_images_to_r2 --dry-run` 无凭据错误

## 参考资源

- [Cloudflare R2 文档](https://developers.cloudflare.com/r2/)
- [R2 S3 API](https://developers.cloudflare.com/r2/api/s3/api/)
- [R2 与 wrangler](https://developers.cloudflare.com/r2/buckets/get-started/)
- [boto3 示例](https://developers.cloudflare.com/r2/examples/boto3/)
