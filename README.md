# SDlab

面向 AI 图像生成模型的**画风对比展示站点**：以 X / Y prompt 网格批量整理各模型在不同画师风格与参数下的产出，发布到线上供浏览、比较与收藏。

线上站点：<https://sdlab.wall-breaker-no4.xyz>

> 除网站外，本仓库还托管作者自用的**生图流水线**。它负责批量生图并发布内容，属于内部工具，不是产品的一部分。

## 网站功能

- **模型网格**：按 run 浏览完整的 X/Y prompt 生成结果，支持虚拟滚动、大图预览与工作流下载
- **画师串收藏**：收藏感兴趣的 Y 轴画师串，并跨模型对比同一风格（`/favorites`）
- **Prompt 法典**：结构化提示词浏览器，按目标模型与权重模式格式化后复制（`/prompts`）
- **模型指南**：与模型绑定的使用经验文章（`/guides`）
- 中／英双语、亮／暗主题、NSFW 偏好开关

## 目录导览

| 路径 | 说明 |
| --- | --- |
| `app/`、`components/`、`lib/`、`i18n/`、`messages/` | 网站：页面、组件、数据层与国际化 |
| `main.py`、`scripts/`、`pyproject.toml` | 生图流水线：生成、上传与 CLI（内部工具，非用户面） |
| `supabase/` | 数据库迁移与本地配置（两侧共享的数据契约） |
| `data/` | 输入资产：生图配置、prompt 资产与网站内容源 |
| `docs/` | 设计决策（ADR）与协作文档 |
| `e2e/`、`tests/` | 端到端与单元测试 |

## 技术栈

- **网站**：Next.js 16（App Router）/ React 19 / Tailwind CSS 4 / next-intl；部署于 Cloudflare（OpenNext），数据来自 Supabase 与 Cloudflare R2
- **流水线**：Python 3.13+ / uv；对接 ComfyUI 与 NovelAI

## 本地运行

```bash
pnpm install
pnpm dev                        # 网站开发服务器

uv sync
uv run python main.py --help    # 生图流水线 CLI
```

环境变量见 `.env.example`；测试：`pnpm test`、`pnpm test:e2e`、`uv run pytest -q`。
