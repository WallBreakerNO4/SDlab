<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-08-23 | Updated: 2026-08-23 -->

# docs/ — 设计决策记录与项目术语表

## Purpose

存放仓库级的设计决策记录（ADR）与项目术语表。它们是**参照性文档**，不是运行时依赖：代码行为以实现为准，术语与决策用于对齐讨论与协作文本。

## Key Files

| File | Description |
|------|-------------|
| `glossary.md` | 项目术语表：定义领域术语（如 Model Guide / `model_key` / `run_dir` / Guide Draft 等），统一讨论与文档用语 |
| `adr/0001-model-guide-content-routing.md` | ADR-0001：模型使用指南的内容契约、路由与模型身份（`model_key` 与 `runDir` 的关系、draft 开关） |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `adr/` | 设计决策记录（RFC 式编号文件）；新增重要架构决策时在此追加 |

## For AI Agents

### Working In This Directory

- 本目录是纯文档，改动不需要构建或测试。
- 引入新的领域术语或重要架构决策时，先补充 `glossary.md` / 追加 ADR，再更新相关代码文档。
- ADR 文件名保持 `NNNN-<slug>.md` 递增编号；已 Accepted 的 ADR 只允许追加修订说明，不直接改写历史决策内容。

## Dependencies

### Internal

- 术语表与 ADR 是根 `AGENTS.md` 及分层文档的参照来源；模型指南相关内容见 `app/[locale]/guides/`、`lib/model-guides.ts`、`data/model-guides/`。

<!-- MANUAL: -->