<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-07-19 -->

# e2e/ — Playwright 端到端测试

## 概览

- E2E 用 Playwright 跑 Next 网站的核心流程与 R2 图片源验证；证据落盘在 `test-results/`（Playwright 官方默认产物目录）。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| Playwright 全局配置 | `playwright.config.ts` | baseURL/webServer/outputDir |
| 冒烟 | `smoke.spec.ts` | 首页可访问 |
| Supabase 配置校验 | `task-10.spec.ts` | 跳过无 Supabase 环境 |
| 主流程 | `task-13-main-flow.spec.ts` | models → detail → grid 完整链路 |
| R2 图片源验证 | `task-13-r2-src.spec.ts` | 图片 src 指向 R2 公开/私有 URL |
| 弹窗按需加载 | `task-13-dialog-on-demand.spec.ts` | 弹窗 display 图片按需加载 |
| hash 跳转 | `task-13-hash-jump.spec.ts` | URL hash 定位到特定 cell |
| 滚动恢复 | `task-13-scroll-restore.spec.ts` | 弹窗关闭后恢复滚动位置 |
| Mixer prompt parts 渲染 | `task-13-mixer-prompt-parts.spec.ts` | Mixer 的 y_prompt_parts（Artist/Common Prompt）前端分栏渲染 |
| 画师串收藏 | `task-14-style-favorites.spec.ts` | 未登录弹登录框/收藏页门控 + 已登录 toggle/面板跳转/收藏页 |
| 已登录态机制 | `global-setup.ts` / `global-teardown.ts` / `e2e-auth-state.ts` | service role admin 链路建 session 写 storageState；teardown 清空测试用户收藏 |

## 运行

```bash
pnpm test:e2e
pnpm test:e2e -- --list
pnpm test:e2e -- -g "task 13"

# 以 start 模式跑（更接近生产；必须用默认 3000 端口，R2 CORS 白名单限定）：
E2E_SERVER=start pnpm test:e2e
```

## 约定（本目录特有）

- `baseURL` 由 `E2E_PORT` 影响（默认 3000）；webServer 命令根据 `E2E_SERVER` 选择 `dev` 或 `build+start`
- baseURL 用 `localhost` 不用 `127.0.0.1`：R2 CORS 只放行 `http://localhost:3000` 与生产域名，`127.0.0.1` 会被 CORS 拒且 dev 模式不 hydrate；start 模式必须用默认 3000 端口
- 证据：测试可写 `test-results/`（`mkdirSync(..., { recursive: true })`），已被根 `.gitignore` 的 `/test-results/` 忽略
- 旧 spec 已清理：task-11 ~ task-16（旧安全/性能/虚拟滚动等）已移除；当前 spec 聚焦 Supabase + R2 流程
- 新增 spec 时命名建议：`task-{N}-{描述}.spec.ts`
- 已登录用例：global setup 用 `SUPABASE_SERVICE_ROLE_KEY` 经 admin API（generate_link + 手工截 fragment tokens + @supabase/ssr cookie 编码）把测试用户 session 写入 `test-results/e2e-auth-state.json`，用例侧 `test.use({ storageState })` 复用；缺环境变量（`.env` 由 `process.loadEnvFile` 加载）时 setup 不写 state、已登录用例 skip；global teardown 清空该测试用户的 `user_style_favorites`

## 反模式

- 不要把 `test-results/` 当源码目录；它是测试产物
- 不要依赖本地 `outputs/` 或任何生图运行目录；E2E 应基于 Supabase + R2 数据源
