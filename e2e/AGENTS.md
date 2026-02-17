# e2e/ — Playwright 端到端测试

## 概览

- E2E 用 Playwright 跑 Next 网站的核心流程、安全回归与虚拟滚动性能；证据落盘在 `.sisyphus/evidence/`。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| Playwright 全局配置 | `playwright.config.ts` | baseURL/webServer/outputDir |
| 冒烟 | `e2e/smoke.spec.ts` | 首页可访问 |
| run 不存在 | `e2e/task-11-run-notfound.spec.ts` | 404 与页面空态 |
| 虚拟滚动 | `e2e/task-12-virtual-scroll.spec.ts` | grid 大数据渲染 |
| 弹窗与复制 | `e2e/task-13-dialog-copy.spec.ts` | 预览 + clipboard |
| 主流程 | `e2e/task-14-main-flow.spec.ts` | runs -> detail -> grid |
| 安全回归 | `e2e/task-15-security.spec.ts` | traversal/泄露检查 |
| 性能 | `e2e/task-16-performance.spec.ts` | 渲染与滚动指标 |

## 运行

```bash
pnpm test:e2e
pnpm test:e2e -- --list
pnpm test:e2e -- -g "task 15"

# 以 start 模式跑（更接近生产）：
E2E_SERVER=start E2E_PORT=3001 pnpm test:e2e
```

## 约定（本目录特有）

- `baseURL` 由 `E2E_PORT` 影响（默认 3000）；webServer 命令根据 `E2E_SERVER` 选择 `dev` 或 `build+start`
- 证据：测试可写 `.sisyphus/evidence/*`（必要时 `mkdirSync(..., { recursive: true })`）
- 安全：对无效 runDir、路径穿越等用例，断言响应体不包含 `/home/`、`C:\\`、`stack`、`Traceback` 等敏感 token

## 反模式

- 不要把 `.sisyphus/evidence/` 当源码目录；它是测试产物
