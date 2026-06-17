<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-17 | Updated: 2026-06-17 -->

# components/prompt/ — Prompt 法典浏览器 UI

## 概览

- 本目录是「Prompt 法典浏览器」（路由 `/[locale]/prompts`）的全部客户端组件：把结构化 Prompt（Tag / Choice / CharacterBlock）渲染为可交互卡片，支持目标模型切换、权重模式切换、Choice 选择、复制格式化文本、TOC 章节导航、Ctrl+F 式匹配导航。
- 数据源是构建期产物 `public/data/prompts/index.json` + `public/data/prompts/files/<id>.json`，由 `lib/prompt-data-loader.ts` 通过 `fetch("/data/prompts/...")` 加载；本目录组件不直接读取 `data/prompt-codex/` 源 YAML。
- 状态边界由两个 Context 承载：`lib/prompt-model-context.tsx`（目标模型 + 权重模式，持久化到 localStorage）与 `lib/prompt-choice-context.tsx`（用户在 Choice 节点上的选择）。页面入口 `app/[locale]/prompts/page.tsx` 用 `ModelProvider` + `ChoiceProvider` 包裹本目录组件。
- 渲染管线：`prompt-browser-page.tsx`（页面骨架 + 数据加载 + 过滤 + 快捷键）→ `prompt-toc-sidebar.tsx`（左侧目录）+ `prompt-entry-list.tsx`（虚拟滚动条目列表）→ `prompt-entry-card.tsx`（单条目卡片）→ `prompt-renderer.tsx`（节点递归渲染）→ `tag-node.tsx` / `choice-node.tsx` / `character-block.tsx`。
- 登录门控：`prompt-browser-page.tsx` 在未登录时渲染登录引导并挂载 `AuthLoginDialog`；法典浏览需要登录态。

## 去哪儿看

| 场景                     | 位置                      | 备注                                                                 |
| ------------------------ | ------------------------- | -------------------------------------------------------------------- |
| 页面骨架 / 状态编排      | `prompt-browser-page.tsx` | 加载索引+文件、URL 同步 `?file=`、过滤、Ctrl+F 导航、IntersectionObserver 章节追踪 |
| 顶部工具栏               | `prompt-top-bar.tsx`      | 文件切换、搜索输入、过滤范围/模式、模型/权重模式切换、匹配计数与上/下条导航 |
| 左侧 TOC 侧栏           | `prompt-toc-sidebar.tsx`  | 桌面侧栏 + 移动端 Sheet fallback，委托 `prompt-toc-tree.tsx`          |
| TOC 树渲染 + key 计算    | `prompt-toc-tree.tsx`     | `nodeKey()` 用 `\0` 拼接路径；展开/折叠、章节高亮                     |
| 虚拟滚动条目列表         | `prompt-entry-list.tsx`   | `@tanstack/react-virtual`；导出 `ScrollTarget` 类型；滚动恢复由 `hooks/use-prompts-scroll-restore.ts` 支持 |
| 单条目卡片               | `prompt-entry-card.tsx`   | `memo` 化；渲染 base + characters + variants；占位符告警；复制按钮    |
| 节点递归渲染             | `prompt-renderer.tsx`     | 遍历 `PromptNode[]`，按 type 分派到 `tag-node` / `choice-node`        |
| Tag 节点                 | `tag-node.tsx`            | Badge 渲染 + 权重/注释 Tooltip；从 `useModel()` 读模型与权重模式       |
| Choice 节点              | `choice-node.tsx`         | Select + 详情 Dialog；选择写入 `useChoices()`，`allow_empty` 支持"不添加" |
| 多角色块                 | `character-block.tsx`     | Tabs 分角色；每角色复用 `prompt-renderer`                             |
| 复制按钮                 | `copy-button.tsx`         | 调 `lib/prompt-formatter.ts:formatPrompt()` 生成目标模型文本，写剪贴板 |

## 约定（本目录特有）

- 所有组件都是 `"use client"`；本目录不出现任何 `server-only` / `next/headers` / 服务端 Supabase 导入。
- 目标模型与权重模式的唯一读取入口是 `useModel()`；不要在子组件里再读 localStorage 或自维护状态。
- Choice 选择的唯一读写入口是 `useChoices()`；`selections` 的 key 由 `prompt-renderer` 的 `pathPrefix` + 节点下标递归拼接而成，不要在组件层手拼 key。
- 格式化文本统一走 `lib/prompt-formatter.ts:formatPrompt()`；不要在 `copy-button.tsx` 之外的组件里自行拼接目标模型字符串。
- 大列表必须虚拟化：`prompt-entry-list.tsx` 使用 `@tanstack/react-virtual`，单卡片用 `memo` 避免重渲染。
- 搜索匹配导航模仿浏览器 Ctrl+F：`/` 或 `Ctrl+F` 聚焦搜索框（`data-prompt-search-input`），`Enter` / `Shift+Enter` 在匹配间跳转；新增输入控件时注意不要拦截这两个快捷键。
- TOC 展开状态与滚动位置都持久化到 localStorage（key 分别为 `toc-expanded` 和由 `hooks/use-prompts-scroll-restore.ts` 管理）；不要把这些状态搬到 URL 或服务端。
- UI 复用 `components/ui/*` primitives（Button / Input / Select / Dialog / Tabs / Badge / Tooltip / ScrollArea / Sheet）；不要引入新的无样式原生控件。

## 反模式

- 不要在本目录组件里直接 `fetch("/data/prompts/...")`；数据加载统一经 `lib/prompt-data-loader.ts`（带缓存）。
- 不要把 `data/prompt-codex/*.yaml` 当运行时数据源；那是源资产，运行时只消费 `public/data/prompts/*.json`。
- 不要在 Tag/Choice 渲染里硬编码模型格式（如手写 `(text:1.5)`）；格式化逻辑只在 `lib/prompt-formatter.ts`。
- 不要绕过 `useChoices()` 直接改 selections；也不要把 selections 提升到页面级 useState（会破坏 Context 更新边界）。
- 不要在条目列表里全量渲染；条目数量可达数千，必须走虚拟滚动。

## Dependencies

### Internal
- `lib/prompt-types.ts` — `TagNode` / `ChoiceNode` / `Prompt` / `Entry` / `TocNode` / `TargetModel` / `WeightMode` / `FilterScope` / `FilterMode` / `FileIndex` / `FileData`
- `lib/prompt-formatter.ts` — `formatPrompt()` / `hasPlaceholders()`
- `lib/prompt-filter.ts` — `filterEntriesExact` / `filterEntriesFuzzy` / `createFilterFuse` / `filterToc` / `getAllTocKeys`
- `lib/prompt-data-loader.ts` — `loadIndex()` / `loadFileData()`
- `lib/prompt-model-context.tsx` — `ModelProvider` / `useModel()`
- `lib/prompt-choice-context.tsx` — `ChoiceProvider` / `useChoices()`
- `hooks/use-prompts-scroll-restore.ts` — 滚动位置存取
- `components/auth-provider.tsx` — `useAuth()` 登录门控
- `components/auth-login-dialog.tsx` — 未登录时挂载
- `components/ui/*` — shadcn/radix primitives

### External
- `@tanstack/react-virtual` — 条目列表虚拟化
- `next-intl` — `useTranslations("prompts")`
- `next/navigation` — `useRouter` / `useSearchParams`（URL `?file=` 同步）
- `lucide-react` — 图标
