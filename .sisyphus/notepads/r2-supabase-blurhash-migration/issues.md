## 2026-02-26

- Next dev 通过 pnpm 启动时，shell PID 可能不是实际持锁的 node 进程；需要用 `pkill -f "next dev -p <port>"` 或 `pgrep -af "next dev"` 精确清理残留进程，避免 `.next/dev/lock` 获取失败。
- `pnpm build` 里 Turbopack 会警告 `lib/comfyui-fs.ts` 对 `comfyui_api_outputs/` 的路径匹配过宽（匹配大量文件）；属于性能提示，不影响本次任务验证。
- 本地未配置 R2 私有桶访问变量（`R2_ENDPOINT/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_PRIVATE_BUCKET`）时，private 代理对“合法 key”会返回 500（R2 not configured）；但对非法 key（如 `original_png`/`.png`/非 runs 前缀）应在本地校验阶段直接 404/400，且不会触发上游请求。
- 未配置 Supabase 环境时，`e2e/task-10.spec.ts` 会因为首页无 runs 链接而超时；需要加 `test.skip()` 门禁与 task 13 的 gating 保持一致。
