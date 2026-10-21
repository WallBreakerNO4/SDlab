<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-09-04 | Updated: 2026-09-04 -->

# docs/ — 设计决策与 agent 协作文档

## 概览

- 本目录存放两类文档：`adr/` 记录不可从代码直接看出的设计决策（ADR，含已考虑选项与后果）；`agents/` 约定各 agent 技能（issue tracker / triage / domain 文档）在本仓库的落地方式。
- 领域术语表在仓库根目录 `CONTEXT.md`（single-context 布局），与本目录的 ADR 配套使用；不建独立 glossary 文件。

## Key Files

| 文件 | 描述 |
|------|------|
| `adr/0001-novelai-anlas-guard.md` | Anlas 守卫初始决策：拒绝一切 Anlas 计费请求；部分被 ADR 0002 取代 |
| `adr/0002-novelai-guard-drops-anlas-balance-check.md` | 移除生成后 Anlas 余额核对；V5 电量耗尽升级为真中止 |
| `agents/domain.md` | agent 如何消费 `CONTEXT.md` 与 `docs/adr/`（single-context 布局约定） |
| `agents/issue-tracker.md` | issue/spec 统一走 GitHub Issues + `gh` CLI 的命令约定 |
| `agents/triage-labels.md` | 五个分诊角色 → 本仓库中文标签的映射 |

## For AI Agents

### Working In This Directory

- 新增 ADR 使用递增四位编号（`NNNN-kebab-case-title.md`），正文含状态行；被后续决策部分取代时，新旧两篇都要用链接互相标注
- ADR 只记录「决策 + 已考虑选项 + 后果」，不记录实现过程；实现细节放代码注释或 issue
- `agents/` 下的文件是 agent 技能的配置面：调整 issue 流程、标签词汇、domain 文档布局时先改这里，再同步根 `AGENTS.md` 的「Agent skills」一节
- 不要把本目录当通用 wiki：只放 agent 协作约定与架构决策

### Common Patterns

- ADR 状态行写法：`> 状态：部分被 [ADR 0002](…) 取代——…` 或 `状态：accepted，部分取代 [ADR 0001](…)`
- 领域术语敲定时同步更新根 `CONTEXT.md` 的 Language 小节（含 `_Avoid_` 反例），由 `/domain-modeling` 等技能惰性维护

## Dependencies

### Internal

- 根 `AGENTS.md` 的「Agent skills」一节引用 `docs/agents/*.md`
- `scripts/generation/novelai_client.py` / `novelai_generate.py` 实现 ADR 0001/0002 约束的守卫行为
- 根 `CONTEXT.md` 的「电池」「Anlas 守卫」「硬停」词条与 ADR 0001/0002 保持一致

<!-- MANUAL: -->
