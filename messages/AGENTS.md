<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-30 | Updated: 2026-08-23 -->

# messages/ — 翻译消息 JSON

## 概览

- 存放 `next-intl` 的翻译消息文件。支持 `zh`（简体中文）和 `en`（英语）。每个 JSON 文件按 namespace 组织：`metadata`、`header`、`home`、`footer`、`auth`、`modelDetail`、`virtualGrid`、`cellDialog`、`modelCard`、`prompts`、`styleFavorites`。

## Key Files

| 文件 | 描述 |
|------|------|
| `zh.json` | 中文翻译消息，默认语言 |
| `en.json` | 英文翻译消息 |

## 翻译 Key 结构

| Namespace | 用途 |
|-----------|------|
| `metadata` | 页面 `<title>` 与 `<meta description>`（home / info / privacy / error / notFound） |
| `header` | 站点头部：品牌名、登录入口、用户菜单、NSFW 切换、主题切换 |
| `home` | 首页：Hero 区文案、模型目录标题、空/错误状态 |
| `footer` | 页脚：版权声明、关于链接、隐私政策链接 |
| `auth` | 登录弹窗：标题、描述、各 OAuth provider 入口文案 |
| `modelDetail` | 模型详情页：面包屑、错误/空状态、外部链接、workflow 下载 |
| `virtualGrid` | 虚拟网格工具面板：搜索、跳转、列显示、复制提示 |
| `cellDialog` | 单元格预览弹窗：prompt、seed、图片下载、翻页 |
| `modelCard` | 首页模型卡片：大图预览、展开收起、横向滚动 |
| `prompts`   | Prompt 法典浏览器:文件切换、搜索、过滤、模型/权重模式、复制、登录门控等 |
| `styleFavorites` | 画师串收藏与模型对比：星标 toggle、收藏面板、登录引导、模型显隐、对比矩阵/详情、加载与错误状态 |

## For AI Agents

### Working In This Directory
- 新增翻译 key 时，必须同时更新 `zh.json` 和 `en.json`；两个文件的 key 结构必须完全一致
- 翻译 key 以 `.` 分隔命名空间，如 `home.title` 对应 namespace `home` 中的 `title`
- 参数化文本使用 ICU MessageFormat 语法，如 `{count} Models Found`、`{current}/{total}`
- 不要在翻译文件中存放 HTML 或 JSX 片段；所有 UI 结构由组件控制

### Common Patterns
- 组件内使用：`const t = useTranslations("home")` → `t("title")`
- 服务端使用：`const t = await getTranslations({ locale, namespace: "metadata.home" })` → `t("title")`

## Dependencies

### Internal
- `i18n/request.ts` - 按 `requestLocale` 动态导入对应 JSON

### External
- `next-intl` - `useTranslations()` / `getTranslations()` 消费本目录消息
