## 2026-02-26

- Next dev 通过 pnpm 启动时，shell PID 可能不是实际持锁的 node 进程；需要用 `pkill -f "next dev -p <port>"` 或 `pgrep -af "next dev"` 精确清理残留进程，避免 `.next/dev/lock` 获取失败。
