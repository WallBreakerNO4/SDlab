# e2e/ — Playwright 端到端测试

## 概览

- E2E 用 Playwright 跑 Next 网站的核心流程与 R2 图片源验证；证据落盘在 `.sisyphus/evidence/playwright/`。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| Playwright 全局配置 | `playwright.config.ts` | baseURL/webServer/outputDir |
| 冒烟 | `smoke.spec.ts` | 首页可访问 |
| Supabase 配置校验 | `task-10.spec.ts` | 跳过无 Supabase 环境 |
| 主流程 | `task-13-main-flow.spec.ts` | runs → detail → grid 完整链路 |
| R2 图片源验证 | `task-13-r2-src.spec.ts` | 图片 src 指向 R2 公开/私有 URL |

## 运行

```bash
pnpm test:e2e
pnpm test:e2e -- --list
pnpm test:e2e -- -g "task 13"

# 以 start 模式跑（更接近生产）：
E2E_SERVER=start E2E_PORT=3001 pnpm test:e2e
```

## 约定（本目录特有）

- `baseURL` 由 `E2E_PORT` 影响（默认 3000）；webServer 命令根据 `E2E_SERVER` 选择 `dev` 或 `build+start`
- 证据：测试可写 `.sisyphus/evidence/playwright/`（`mkdirSync(..., { recursive: true })`）
- 旧 spec 已清理：task-11 ~ task-16（旧安全/性能/虚拟滚动等）已移除；当前 spec 聚焦 Supabase + R2 流程
- 新增 spec 时命名建议：`task-{N}-{描述}.spec.ts`

## 反模式

- 不要把 `.sisyphus/evidence/` 当源码目录；它是测试产物
- 不要假设本地 `comfyui_api_outputs/` 存在数据；E2E 应基于 Supabase + R2 数据源
