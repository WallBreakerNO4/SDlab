## 2026-02-26

- Next dev 会自动加载 `.env`；想验证“缺失 Supabase env”时，单纯 `env -u ...` 不可靠，建议在启动进程前显式设置空值：`SUPABASE_URL= SUPABASE_SERVICE_ROLE_KEY=`。
- `import 'server-only'` 在 Next 构建/运行可用，但在裸 Node 环境下无法 `require('server-only')`，因此本地脚本验证应走 Next route/runner。
- 本仓库里 `pnpm run dev -p 3005` 传参可用；使用 `--` 会导致 Next 将后续参数当成 directory。
