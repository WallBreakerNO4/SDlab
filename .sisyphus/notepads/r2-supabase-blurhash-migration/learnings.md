## 2026-02-26

- Next dev 会自动加载 `.env`；想验证“缺失 Supabase env”时，单纯 `env -u ...` 不可靠，建议在启动进程前显式设置空值：`SUPABASE_URL= SUPABASE_SERVICE_ROLE_KEY=`。
- `import 'server-only'` 在 Next 构建/运行可用，但在裸 Node 环境下无法 `require('server-only')`，因此本地脚本验证应走 Next route/runner。
- 本仓库里 `pnpm run dev -p 3005` 传参可用；使用 `--` 会导致 Next 将后续参数当成 directory。
- `/api/comfyui/run/[runDir]` 已改为从 Supabase `runs` 表按 `run_dir` 精确查询；输入用 `isValidRunDir()` 校验，不通过直接 404，避免走旧的本地 allowlist/fs 逻辑。
- 安全回归里使用 `../../etc/passwd` 这类 path traversal 时，Next 可能在路由层就直接回 404 HTML（不进入 handler）；但响应体不应包含本机路径/stack。
- VirtualGrid 改为“按行懒加载”：组件仅拿 `x_columns/y_indexes`，渲染可视行时增量请求 `/api/comfyui/run/${runDir}/row?y_index=...`（包含 overscan），避免首屏把整张 grid 的 cell 元数据一次性拉满。
- 行数据缓存用 `Map<y_index, payload>`，并对 in-flight request 维护 `AbortController`；组件卸载时统一 abort，避免滚动/切页残留请求。
- 图片渲染用 `<picture>`（优先 `avif`，fallback `webp`），Dialog 预览强制用 `display` 变体；不再走 `/api/comfyui/image/` 以及 `next/image` 优化链。
- `/api/comfyui/runs` 从 Supabase `runs` 表读取：`select run_dir, created_at, run_json`；`run_id` 取 `run_json.run_id`，缺失回退 `run_dir`；计数优先 `selection.x_columns/y_indexes` 长度，缺失再回退 `selection.x_count/y_count`，最终缺失为 0。
- BlurhashCanvas 使用 fast-blurhash 的 decodeBlurHash，并需要将返回的 Uint8ClampedArray 强转为 any 才能传入 ImageData 构造函数（TypeScript 5.5+ 类型定义问题）。
- run 详情页 `app/runs/[runDir]/page.tsx` 保持并行拉取 run detail + grid index；grid 仅以 `x_columns/y_indexes` 为结构输入传给 `VirtualGrid`，避免旧的 `cells` 全量模型，滚动时由 `VirtualGrid` 触发 row 懒加载。
- private 图片代理使用 Next Route Handler + `aws4fetch` 的 `AwsClient` 对 `R2_ENDPOINT` 发起签名请求；路由参数需要逐段 decode/join，再逐段 encode 进上游 URL，且要显式拒绝 `%2F/%5C` 这类“段内编码斜杠”。
- 私有代理必须支持 `HEAD`（curl -I / 浏览器探测会用到）；错误响应只给短文案，不回显 endpoint/bucket/key，可用 `sha256(key).slice(0,12)` 作为日志关联 id。
- Documented Cloudflare Workers deployment with OpenNext for Next.js applications.
- Using dedicated API Routes for R2 private asset proxying is more robust than Middleware in Edge/Worker environments.
- Playwright E2E 中只要依赖 Supabase 数据（runs 列表 / run 详情 / row 懒加载），在缺少 `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` 时应统一 `test.skip()`，避免本地默认环境红灯。
- R2 直链断言优先使用 `R2_PUBLIC_BASE_URL`：`img[data-testid=run-grid-image]` 的 `src` 应以 `${R2_PUBLIC_BASE_URL}/` 开头，且不包含 `/api/comfyui/image/`。
