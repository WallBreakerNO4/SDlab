# Domain 文档

工程技能在探索代码库时应如何消费本仓库的领域文档。

## 探索前先读这些

- 仓库根目录的 **`CONTEXT.md`**；
- 若存在根目录 **`CONTEXT-MAP.md`**：它会指向每个 context 各自的 `CONTEXT.md`，读取与主题相关的那些；
- **`docs/adr/`**：阅读与你将要工作的区域相关的 ADR。多 context 仓库还需检查 `src/<context>/docs/adr/` 下的 context 级决策。

若上述文件不存在，**静默继续**。不要提示缺失，也不要建议提前创建。`/domain-modeling` 技能（经 `/grill-with-docs` 与 `/improve-codebase-architecture` 进入）会在术语或决策真正敲定时惰性创建它们。

## 文件结构

单一 context 仓库（绝大多数仓库属于此类）：

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

多 context 仓库（根目录存在 `CONTEXT-MAP.md` 时）：

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← 全系统级决策
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← context 级决策
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

本仓库采用 **single-context** 布局。

## 使用术语表的词汇

输出中出现领域概念时（issue 标题、重构提案、假设、测试命名等），使用 `CONTEXT.md` 中定义的术语。不要漂移到术语表明确避免的同义词。

如果所需概念还不在术语表中，这是一个信号：要么你正在发明项目不用的语言（请重新考虑），要么存在真实缺口（记下来交给 `/domain-modeling`）。

## 标记 ADR 冲突

如果你的输出与既有 ADR 矛盾，显式指出而不是默默覆盖：

> _Contradicts ADR-0007 (event-sourced orders), but worth reopening because…_
