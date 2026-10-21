<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-08-23 -->

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
| 画师串收藏 | `task-14-style-favorites.spec.ts` | 未登录弹登录框/收藏页门控 + 已登录 toggle/面板跳转/收藏页 + 对比页 BlurHash 回退 |
| 首页评测状态 | `task-11-homepage-status.spec.ts` | no-env mock 下的首页排序（published_at）与「评测中」徽章（中英文） |
| 详情页评测状态 | `task-13-pre-release-status.spec.ts` | mock 当前的 `status`：进行中横幅（中英文）、「待生成」/「缺失」占位、缺状态字段按已完结 |
| 对比页评测状态 | `task-13-comparison-status.spec.ts` | 已登录用例（缺 Supabase 环境变量时 skip）：进行中评测禁用条目 + 徽章 + 说明，矩阵与 slice 只含已完结评测 |
| no-env mock 运行时 | `no-env-webserver.cjs`、`mock-supabase-rest.cjs`、`no-env-home-run-list.json` | 假 Supabase REST 端点 + next build/start 启动器 + 首页固定数据 |
| 模型详情顶栏 Markdown | `model-detail-markdown.spec.ts` | mock 模式下渲染允许的 Markdown，并验证链接安全属性（外链新窗口/禁图等） |
| model view 合约 | `model-view-test-helpers.spec.ts` | 校验 mock helper 的 URL 契约（公开/私有变体 pattern） |
| model view mock 工具 | `model-view-test-helpers.ts` | `MOCK_MODEL_VIEW_RUN_DIR` 等 mock run 常量与 URL pattern；`runStatus` / `emptyRowIndexes` / `failedRowIndexes` 可构造进行中评测、无图单元格与加载失败行 |
| no-env blocker 验证 | `no-env-blocker.spec.ts` | 验证 no-env 配置下 worker 预加载了环境文件阻断器（配合 `no-env-node-options.ts` / `env-file-path.cjs`） |
| 已登录态机制 | `global-setup.ts` / `global-teardown.ts` / `e2e-auth-state.ts` | service role admin 链路建 session 写 storageState；teardown 清空测试用户收藏 |

## 运行

```bash
pnpm test:e2e
pnpm test:e2e -- --list
pnpm test:e2e -- -g "task 13"

# 以 start 模式跑（更接近生产；必须用默认 3000 端口，R2 CORS 白名单限定）：
E2E_SERVER=start pnpm test:e2e

# 无密钥公开/mock 套件：阻断 .env*、禁用登录 setup、使用 localhost 假 public 配置
./node_modules/.bin/playwright test --config=playwright.no-env.config.ts
```

## 约定（本目录特有）

- `baseURL` 由 `E2E_PORT` 影响（默认 3000）；webServer 命令根据 `E2E_SERVER` 选择 `dev` 或 `build+start`
- baseURL 用 `localhost` 不用 `127.0.0.1`（R2 CORS 只放行 `http://localhost:3000` 与生产域名）；start 模式必须用默认 3000 端口
- 证据：测试可写 `test-results/`（`mkdirSync(..., { recursive: true })`），已被根 `.gitignore` 的 `/test-results/` 忽略
- 新增 spec 时命名建议：`task-{N}-{描述}.spec.ts`
- 已登录用例：global setup 用 `SUPABASE_SERVICE_ROLE_KEY` 经 admin API（generate_link + 手工截 fragment tokens + @supabase/ssr cookie 编码）把测试用户 session 写入 `test-results/e2e-auth-state.json`，用例侧 `test.use({ storageState })` 复用；缺环境变量（`.env` 由 `process.loadEnvFile` 加载）时 setup 不写 state、已登录用例 skip；global teardown 清空该测试用户的 `user_style_favorites`
- 无密钥入口：`playwright.no-env.config.ts` 不注册 global setup/teardown，先构建再启动 3100 端口；`e2e/block-env-file-access.cjs` 同时阻断测试进程与 Next 子进程读取 `.env*`，清除继承的 service-role 变量，测试产物只写 `/tmp/sdlab-playwright-no-env/`
- no-env webServer 走 `e2e/no-env-webserver.cjs`：先启动 `e2e/mock-supabase-rest.cjs` 的假 Supabase REST 端点（固定数据在 `e2e/no-env-home-run-list.json`），再执行 `next build` / `next start`，保证首页与详情页的服务端渲染查询在无密钥模式下有确定性数据

## 反模式

- 不要把 `test-results/` 当源码目录；它是测试产物
- 不要依赖本地 `outputs/` 或任何生图运行目录；E2E 应基于 Supabase + R2 数据源
