# Issue Tracker：GitHub

本仓库的 issue 与 spec 统一存放在 GitHub Issues 中，所有操作均使用 `gh` CLI 完成。

## 约定

- **创建 issue**：`gh issue create --title "..." --body "..."`。多行 body 使用 heredoc。
- **查看 issue**：`gh issue view <number> --comments`，用 `jq` 过滤评论并同时获取 labels。
- **列出 issue**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，按需追加 `--label` 与 `--state` 过滤。
- **评论 issue**：`gh issue comment <number> --body "..."`
- **添加 / 移除标签**：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **关闭**：`gh issue close <number> --comment "..."`

在克隆目录内运行时，`gh` 会自动从 `git remote -v` 推断目标仓库。

## Pull requests 是否作为分诊入口

**PRs as a request surface: no.**

设为 `yes` 时，PR 会走与 issue 相同的标签与状态流，使用对应的 `gh pr` 命令：

- **查看 PR**：`gh pr view <number> --comments`；diff 用 `gh pr diff <number>`。
- **列出待分诊的外部 PR**：`gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`，仅保留 `authorAssociation` 为 `CONTRIBUTOR`、`FIRST_TIME_CONTRIBUTOR` 或 `NONE` 的条目（剔除 `OWNER`/`MEMBER`/`COLLABORATOR`）。
- **评论 / 打标签 / 关闭**：`gh pr comment`、`gh pr edit --add-label`/`--remove-label`、`gh pr close`。

GitHub 上 issue 与 PR 共用一个编号空间，因此裸 `#42` 可能是两者之一：先 `gh pr view 42`，失败再回退 `gh issue view 42`。

## 当技能说「发布到 issue tracker」时

创建一个 GitHub issue。

## 当技能说「获取相关工单」时

运行 `gh issue view <number> --comments`。

## Wayfinder 操作

供 `/wayfinder` 使用。**map** 是一条带有若干 **child** 子工单的 issue。

- **Map**：单条 issue，标签 `wayfinder:map`，正文承载 Notes / Decisions-so-far / Fog。创建命令：`gh issue create --label wayfinder:map`。
- **Child 工单**：以 GitHub sub-issue 形式挂到 map 下（通过 sub-issues 端点的 `gh api`）。sub-issue 不可用时，把 child 加入 map 正文的任务列表，并在 child 正文顶部注明 `Part of #<map>`。标签：`wayfinder:<type>`（`research` / `prototype` / `grilling` / `task`）。工单被认领后 assign 给驱动开发的会话。
- **阻塞关系**：使用 GitHub 原生 issue dependencies，这是规范且 UI 可见的表达。添加边：`gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`，其中 `<blocker-db-id>` 是 blocker 的数字 **database id**（`gh api repos/<owner>/<repo>/issues/<n> --jq .id` 取得，不是 `#编号` 也不是 `node_id`）。GitHub 通过 `issue_dependencies_summary.blocked_by` 报告开放阻塞数（实时门控）。依赖功能不可用时，回退为在 child 正文顶部写一行 `Blocked by: #<n>, #<n>`。所有 blocker 关闭即视为解锁。
- **Frontier 查询**：列出 map 的 open children（`gh issue list --state open`，限定在 map 的 sub-issues / 任务列表范围内），剔除存在 open blocker（`issue_dependencies_summary.blocked_by > 0`，或 Blocked by 行中有 open issue）或已有 assignee 的条目；按 map 顺序取第一个。
- **认领**：`gh issue edit <n> --add-assignee @me`，作为该会话对工单的首次写入。
- **解决**：`gh issue comment <n> --body "<answer>"`，然后 `gh issue close <n>`，再把上下文指针（gist + 链接）追加到 map 的 Decisions-so-far。
