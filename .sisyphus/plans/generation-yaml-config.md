# 生图 YAML 运行配置迁移计划

## TL;DR
> **Summary**: 将当前依赖 `.env` 的生图业务参数迁移为每次运行显式传入的 YAML 配置，同时保留少量运行环境变量，并把模型展示元数据与配置快照写入 `run.json` 以支持回放、重试和未来网站展示。
> **Deliverables**:
> - 新的 per-run YAML schema 与加载/校验层
> - `--config` 驱动的生成入口
> - 保持 replay/retry/R2 upload 兼容的 `run.json` 扩展快照
> - TDD 覆盖 CLI、schema、dry-run、replay/retry、deprecated env 行为
> **Effort**: Medium
> **Parallel**: YES - 2 waves
> **Critical Path**: 1 -> 2 -> 3 -> 4 -> 5 -> 6

## Context
### Original Request
将当前放在 `.env` 的生图参数迁移到每次运行使用的 YAML 配置文件；该 YAML 同时承载提示词输入引用与模型元数据（链接、描述等），未来供网站展示多个模型的运行结果。

### Interview Summary
- 业务生图参数迁入 YAML；只保留少量运行环境变量。
- 保留在环境层的固定集合：`COMFYUI_BASE_URL`、`COMFYUI_OUT_DIR`、`COMFYUI_REQUEST_TIMEOUT_S`、`COMFYUI_JOB_TIMEOUT_S`、`COMFYUI_CONCURRENCY`。
- 新 YAML 的 prompt 输入采用“引用现有 `data/prompts/**` 资产路径”，不内嵌 X/Y prompt 矩阵正文。
- 运行配置 YAML 放在 `data/runs/`，并作为输入资产纳入 git 追踪。
- 测试策略采用 TDD。
- 输出侧必须保留足够的配置快照与模型元数据，保证 replay/retry 兼容并为未来网站展示预留数据。

### Metis Review (gaps addressed)
- 明确 `run.json` 不仅被 replay/retry 消费，也被 R2 上传和 Supabase 写入链路透传消费。
- 明确 `dry_run`、`retry_*`、`run_dir`、`client_id` 属于运行控制，不进入 per-run YAML。
- 明确 `COMFYUI_APPEND_NEGATIVE_PROMPT` 是业务逻辑的一部分，必须迁入 YAML/`run.json` 快照，不能在迁移时遗漏。
- 明确路径解析、deprecated env 行为、未知 key / schema version 错误都要做硬失败与测试覆盖。

## Work Objectives
### Core Objective
让“新建一次生图运行”的业务输入只来自显式 YAML 配置文件，而不是 `.env`；同时不破坏现有 replay/retry/R2 upload 以及 `run.json` 合约的核心能力。

### Deliverables
- 新增 `scripts/generation/runner_config.py`（或等价命名）的配置加载/校验模块。
- 新增 `--config` CLI 入口，并将 fresh run 的业务配置全部从 YAML 注入。
- 扩展 `run.json`：保留 legacy replay 字段，新增 config/model 快照字段。
- 扩展 replay/retry：能够消费新 `run.json`，并继续兼容旧 `run.json`。
- 新增/更新 pytest 测试，覆盖配置 schema、dry-run、负面提示词追加、deprecated env、replay/retry、R2 upload 兼容。

### Definition of Done (verifiable conditions with commands)
- `uv run pytest -q tests/test_runner_config.py tests/test_runner_dry_run.py tests/test_run_replay.py`
- `uv run pytest -q tests/test_negative_prompt_append.py tests/test_retry_incomplete_integration.py tests/test_idempotent_retry_failed.py`
- `uv run pytest -q tests/test_main_entrypoint.py tests/test_r2_upload_cli_contract.py tests/test_r2_upload_cli_dry_run.py`
- fresh run 必须要求 `--config`；retry 模式不得要求 `--config`。
- `run.json` 同时包含 legacy replay 核心字段和新增的 config/model 快照字段。
- 设置已废弃业务 `COMFYUI_*` 环境变量时不得悄悄覆盖 YAML。

### Must Have
- YAML schema version 与未知 key 硬失败校验。
- repo-relative 路径解析与 sha256 快照。
- 运行配置 YAML 固定存放在 `data/runs/`，并作为 git-tracked 输入资产管理。
- `append_negative_prompt` 正式迁入 YAML 业务配置。
- 运行控制与业务配置明确分层。
- 旧 run 目录 replay/retry 继续可用。

### Must NOT Have
- 不修改 `app/**`、Supabase schema、R2 上传业务逻辑边界。
- 不把 X/Y prompt 正文内嵌进新 config。
- 不让 deprecated 业务 env 与 `--config` 同时生效且无提示。
- 不删除 `run.json` 现有 replay 核心字段。
- 不把大体积 workflow/model 原始对象整段塞进 `run.json`。

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: TDD + pytest
- QA policy: Every task has agent-executed scenarios
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks for max parallelism.

Wave 1: 契约先行（测试、schema 设计、CLI/runtime 边界）
Wave 2: 生成链路与下游收口（payload 快照、replay/retry、negative prompt 迁移、R2 upload 兼容、示例/帮助文本、全量回归）

### Dependency Matrix (full, all tasks)
| Task | Depends On | Blocks |
| --- | --- | --- |
| 1 | - | 2, 3, 4, 5, 6, 7 |
| 2 | 1 | 3, 4, 5, 6 |
| 3 | 1, 2 | 4, 5, 6 |
| 4 | 2, 3 | 5, 7 |
| 5 | 2, 3, 4 | 6, 7 |
| 6 | 2, 3, 5 | 7 |
| 7 | 4, 5, 6 | Final Verification |

### Agent Dispatch Summary (wave -> task count -> categories)
- Wave 1 -> 3 tasks -> `unspecified-high`, `deep`
- Wave 2 -> 4 tasks -> `unspecified-high`, `deep`

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [x] 1. 先写 YAML 配置与入口契约测试

  **What to do**: 先新增失败测试，锁定新行为。创建 `tests/test_runner_config.py`，并更新 `tests/test_runner_dry_run.py`、`tests/test_main_entrypoint.py`、`tests/test_run_replay.py`、`tests/test_negative_prompt_append.py` 的契约断言。测试必须覆盖：fresh run 必须传 `--config`、repo-relative 路径解析、未知 key / 错误 `schema_version` 硬失败、deprecated 业务 env 不得覆盖 YAML、`run.json` 必须保留 legacy replay 字段并新增 config/model 快照字段、`append_negative_prompt` 来自 config 而不是 env。
  **Must NOT do**: 不要先改实现再补测试；不要依赖人工打开 `run.json` 目视检查。

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: 同时涉及 CLI、契约、回放和负面提示词逻辑的测试基线整理。
  - Skills: `[]` - 现有 pytest 模式已足够。
  - Omitted: `['git-master']` - 当前不是 git 操作。

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 2, 3, 4, 5, 6, 7 | Blocked By: -

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `tests/test_runner_dry_run.py:110` - 现有 CLI/help、dry-run、`run.json`/`metadata.jsonl` 合约主参考。
  - Pattern: `tests/test_run_replay.py:22` - 现有 replay 对 `run.json` 核心字段的严格 fixture 模式。
  - Pattern: `tests/test_main_entrypoint.py:10` - 顶层入口创建 `run.json` 的最小 smoke 契约。
  - Pattern: `tests/test_negative_prompt_append.py` - 当前 `append_negative_prompt` 的业务行为与函数契约。
  - API/Type: `scripts/generation/runner_payload.py:40` - `run.json` 当前输出字段基线。
  - API/Type: `scripts/generation/run_replay.py:45` - replay 严格解析入口。

  **Acceptance Criteria** (agent-executable only):
  - [ ] `uv run pytest -q tests/test_runner_config.py` 新增失败测试覆盖 schema、deprecated env、`run.json` 快照。
  - [ ] `uv run pytest -q tests/test_runner_dry_run.py tests/test_main_entrypoint.py tests/test_run_replay.py tests/test_negative_prompt_append.py` 至少有与新需求相关的失败断言，且失败原因指向未实现功能而不是测试写错。

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: 新契约测试先失败且失败点正确
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_runner_config.py tests/test_runner_dry_run.py tests/test_run_replay.py`
    Expected: 退出码非 0；失败点集中在 `--config`、schema 校验、run.json 新字段、append_negative_prompt 迁移等新需求上
    Evidence: .sisyphus/evidence/task-1-config-contract-red.txt

  Scenario: 旧行为测试仍有基线保护
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_main_entrypoint.py tests/test_negative_prompt_append.py`
    Expected: 若失败，失败内容必须由新契约引起；不得出现无关语法/导入错误
    Evidence: .sisyphus/evidence/task-1-baseline-red.txt
  ```

  **Commit**: NO | Message: `test(generation): 锁定 YAML 配置迁移契约` | Files: `tests/test_runner_config.py`, `tests/test_runner_dry_run.py`, `tests/test_main_entrypoint.py`, `tests/test_run_replay.py`, `tests/test_negative_prompt_append.py`

- [x] 2. 新增统一的 YAML 配置 schema、加载与路径校验层

  **What to do**: 新增独立配置模块，负责读取 `--config` 指向的 YAML，并输出强类型/结构化配置对象。Schema 固定为：`schema_version: image-run-config/v1`；`model` 节点含 `key`、`name`、`family`、`links`、`description`、`tags`，其中 `key`/`name`/`family` 为必填非空字符串，`links` 固定键为 `homepage`/`huggingface`/`civitai`（值可为 `null`），`description` 固定键为 `zh`/`en`（允许空字符串），`tags` 为字符串列表；`prompts` 节点含 `x_path`、`y_path`，均为必填 repo-relative 路径；`workflow` 节点含 `path`、`ksampler_node_id`，其中 `path` 为必填 repo-relative `.json` 路径、`ksampler_node_id` 可为 `null`；`generation` 节点含 `template`、`base_seed`、`negative_prompt`、`append_negative_prompt`、`width`、`height`、`batch_size`、`steps`、`cfg`、`denoise`、`sampler_name`、`scheduler`，其中 `template`、`base_seed`、`append_negative_prompt` 为必填键，`append_negative_prompt: null` 表示显式禁用追加，其余键可为 `null`；`selection` 节点含 `x_limit`、`y_limit`、`x_indexes`、`y_indexes`，键必须存在但值可为 `null`。路径只接受仓库内相对路径；prompt 资产允许 `.yaml`/`.yml`/`.json`，workflow 只接受 `.json`，且 fresh run（包括 dry-run）必须验证这些文件存在。加载器必须同时给出 repo-relative 原始引用、解析后的 `Path`、文件 sha256；未知 key、缺失必填、错误 schema version 直接报错。
  **Must NOT do**: 不要把 prompt 文件正文或 workflow JSON 原文读进配置快照；不要接受绝对路径或仓库外路径。

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: 需要把 schema、路径安全、hash 与错误消息一次性定准。
  - Skills: `[]` - 本地 YAML/Path 处理即可。
  - Omitted: `['cloudflare']` - 无外部平台相关性。

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 3, 4, 5, 6 | Blocked By: 1

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `scripts/generation/prompt_grid.py:62` - 现有 X prompt YAML/JSON 资产读取模式。
  - Pattern: `scripts/generation/prompt_grid.py:135` - 现有 Y prompt YAML/JSON 资产读取模式。
  - Pattern: `data/prompts/X/common_prompts.yaml:1` - X 资产真实 YAML 结构样例。
  - Pattern: `data/prompts/Y/300_NAI_Styles_Table-test.yaml:1` - Y 资产真实 YAML 结构样例。
  - Pattern: `scripts/generation/runner_env.py:16` - 当前 env 读取工具；新 loader 不应继续复用它承载业务参数。
  - API/Type: `pyproject.toml:7` - 已有 `pyyaml` 依赖，无需新增包。

  **Acceptance Criteria** (agent-executable only):
  - [ ] `uv run pytest -q tests/test_runner_config.py -k schema` 通过。
  - [ ] 加载器对 repo 外路径、未知 key、错误 `schema_version`、缺失必填字段都返回明确错误消息。
  - [ ] 加载结果同时提供 `config_sha256`、prompt/workflow 文件 sha256 与紧凑模型元数据快照输入。

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: 合法 config 成功加载并解析 repo-relative 路径
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_runner_config.py -k "happy_path or repo_relative"`
    Expected: 退出码 0；断言拿到解析后的 Path、原始 repo-relative 字符串和 sha256
    Evidence: .sisyphus/evidence/task-2-config-loader.txt

  Scenario: 非法 config 硬失败
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_runner_config.py -k "unknown_key or schema_version or path_escape"`
    Expected: 退出码 0；测试断言明确错误文案，不允许静默忽略
    Evidence: .sisyphus/evidence/task-2-config-loader-error.txt
  ```

  **Commit**: NO | Message: `feat(generation): 增加 YAML 运行配置加载器` | Files: `scripts/generation/runner_config.py`, `tests/test_runner_config.py`

- [x] 3. 重构 CLI 与运行时分层，只保留 runtime 入口在 parser/env

  **What to do**: 将 fresh run 改为必须提供 `--config`。`build_parser()` 对外只保留运行控制与环境层参数：`--config`、`--run-dir`、`--dry-run`、`--retry-failed`、`--retry-incomplete`、`--retry-error-code`、`--base-url`、`--request-timeout-s`、`--job-timeout-s`、`--concurrency`、`--client-id`。业务字段不再作为 public CLI 参数，也不再由 env 默认值直接注入；而是由配置加载器在 fresh run 之前写入内部 namespace 字段（沿用现有字段名 `x_json`、`y_json`、`template`、`base_seed`、`workflow_json`、`ksampler_node_id`、`negative_prompt`、`append_negative_prompt`、`width`、`height`、`batch_size`、`steps`、`cfg`、`denoise`、`sampler_name`、`scheduler`、`x_limit`、`y_limit`、`x_indexes`、`y_indexes`），以减少下游 runner 改动。保留 `.env` autoload 仅用于 5 个约定的 runtime env。定义 deprecated 业务 env 名单；fresh run 使用 `--config` 时若检测到这些变量被设置，直接报错并列出变量名。retry/replay 路径不需要 `--config`，继续由 `run.json` 回放填充内部字段。
  **Must NOT do**: 不要把 `dry_run`、`retry_*`、`run_dir`、`client_id` 塞进 YAML；不要让 deprecated 业务 env 与 YAML 同时生效。

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: 涉及 CLI、parser、namespace 注入、retry 分支与 backward compatibility 的分层重构。
  - Skills: `[]` - 现有 argparse 结构即可。
  - Omitted: `['git-master']` - 非 git 任务。

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 4, 5, 6 | Blocked By: 1, 2

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `scripts/generation/comfyui_part1_generate.py:138` - 当前 parser 定义，现有业务参数全部在此公开暴露。
  - Pattern: `scripts/generation/comfyui_part1_generate.py:282` - fresh run 主流程入口，适合插入 config 加载与 namespace 注入。
  - Pattern: `scripts/generation/comfyui_part1_generate.py:562` - 当前参数校验入口，适合加入 `--config` 必填与 deprecated env 错误。
  - Pattern: `main.py:27` - 顶层仍会 autoload dotenv；变更后只能服务 runtime env。
  - API/Type: `scripts/generation/runner_retry.py:9` - retry 目前通过回放把字段写回 argparse namespace，新的 fresh run 注入方式必须与此兼容。
  - API/Type: `scripts/generation/output_packager.py:22` - `COMFYUI_OUT_DIR` 的隐藏 env 耦合必须保留在 runtime 层。

  **Acceptance Criteria** (agent-executable only):
  - [ ] `uv run pytest -q tests/test_main_entrypoint.py tests/test_runner_dry_run.py -k "config or dry_run or help"` 通过。
  - [ ] fresh run 未传 `--config` 时明确报错；retry 模式未传 `--config` 不报该错。
  - [ ] 设置 deprecated 业务 env 并运行 `--config` fresh run 时明确失败，且错误信息包含变量名列表。

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: fresh run 必须使用 --config
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_main_entrypoint.py tests/test_runner_dry_run.py -k "require_config_for_fresh_run"`
    Expected: 退出码 0；测试断言未传 `--config` 时为明确 usage/ValueError，retry 分支不受影响
    Evidence: .sisyphus/evidence/task-3-cli-config-required.txt

  Scenario: deprecated 业务 env 被阻止
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_runner_config.py -k deprecated_env`
    Expected: 退出码 0；测试断言 `COMFYUI_NEGATIVE_PROMPT`、`COMFYUI_X_JSON`、`COMFYUI_APPEND_NEGATIVE_PROMPT` 等不会静默覆盖 YAML
    Evidence: .sisyphus/evidence/task-3-cli-deprecated-env.txt
  ```

  **Commit**: NO | Message: `refactor(generation): 收敛为 config 驱动的 fresh run 入口` | Files: `scripts/generation/comfyui_part1_generate.py`, `scripts/generation/runner_env.py`, `main.py`, `tests/test_main_entrypoint.py`, `tests/test_runner_dry_run.py`

- [x] 4. 扩展 `run.json` 快照，兼容 replay 并承载模型展示元数据

  **What to do**: 更新 `scripts/generation/runner_payload.py` 与相关测试，保留现有 legacy top-level 字段：`x_json_path`、`y_json_path`、`x_json_sha256`、`y_json_sha256`、`template`、`base_seed`、`workflow_json_path`、`workflow_json_sha256`、`selection`、`generation_overrides`；同时新增以下 top-level 字段，命名固定：`config_schema_version`、`config_path`、`config_sha256`、`model`、`config_snapshot`。其中 `model` 仅包含紧凑展示字段：`key`、`name`、`family`、`links`、`description`、`tags`。`config_snapshot` 固定包含：`prompts`（`x_path`、`y_path`、`x_sha256`、`y_sha256`）、`workflow`（`path`、`sha256`、`ksampler_node_id`）、`generation`（`template`、`base_seed`、`negative_prompt`、`append_negative_prompt`、`width`、`height`、`batch_size`、`steps`、`cfg`、`denoise`、`sampler_name`、`scheduler`）、`selection`（`x_limit`、`y_limit`、`x_indexes`、`y_indexes`）。同步将 `generation_overrides` 扩展加入 `append_negative_prompt`，但不要移除旧键。禁止把 prompt 正文、workflow JSON 原文或大体积模型对象内嵌进 `run.json`。
  **Must NOT do**: 不要改变 `run_dir`、`selection.x_columns`、`comfyui_base_url` 等既有字段语义；不要让新增快照替代 legacy replay 字段。

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: 是整个迁移的核心合约，影响生成、回放、上传和未来网站展示。
  - Skills: `[]` - 本地 JSON/Path/hash 逻辑即可。
  - Omitted: `['supabase-postgres-best-practices']` - 本任务不改数据库 schema。

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 5, 7 | Blocked By: 2, 3

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `scripts/generation/runner_payload.py:14` - 当前 `run.json` 生成逻辑。
  - Pattern: `scripts/generation/comfyui_part1_generate.py:311` - `run_payload` 写入 `run.json` 的调用链。
  - Pattern: `tests/test_runner_dry_run.py:188` - 现有 `run.json` 字段断言模式。
  - Pattern: `tests/test_run_replay.py:22` - 现有 replay fixture 必须继续成立。
  - API/Type: `scripts/generation/output_packager.py:22` - `run_dir`/`run.json` 路径约定来源。
  - API/Type: `scripts/r2_upload/upload_discovery.py:63` - 下游依赖 `run_json["run_dir"]` 解析 run 名称。

  **Acceptance Criteria** (agent-executable only):
  - [ ] `uv run pytest -q tests/test_runner_dry_run.py tests/test_run_replay.py -k "run_json or snapshot"` 通过。
  - [ ] 新 `run.json` 同时保留 legacy replay 核心字段与新增 `config_schema_version` / `config_path` / `config_sha256` / `model` / `config_snapshot`。
  - [ ] `generation_overrides.append_negative_prompt` 存在且可为 `null`。

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: dry-run 生成的新 run.json 同时包含 legacy + 新快照字段
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_runner_dry_run.py -k "run_json_snapshot"`
    Expected: 退出码 0；断言 `run.json` 既有 `x_json_path` 等老字段，也有 `config_snapshot.generation.append_negative_prompt` 与 `model.links`
    Evidence: .sisyphus/evidence/task-4-run-json-snapshot.txt

  Scenario: 快照保持紧凑，不嵌入大对象
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_runner_config.py -k "snapshot_compact"`
    Expected: 退出码 0；测试断言 `run.json` 未内嵌 prompt items 或 workflow JSON 原文
    Evidence: .sisyphus/evidence/task-4-run-json-snapshot-error.txt
  ```

  **Commit**: NO | Message: `feat(generation): 为 run.json 增加配置与模型快照` | Files: `scripts/generation/runner_payload.py`, `tests/test_runner_dry_run.py`, `tests/test_run_replay.py`

#WB|- [x] 5. 更新 replay/retry 桥接，兼容新旧 `run.json`

  **What to do**: 扩展 `scripts/generation/run_replay.py` 的 `RunReplayConfig` 与解析逻辑，使其继续要求 legacy replay 核心字段，同时新增可选支持 `generation_overrides.append_negative_prompt` 与 `config_snapshot.workflow.ksampler_node_id`。若新字段不存在（旧 run），保持兼容；若存在，则回放时必须写回 argparse namespace。更新 `scripts/generation/runner_retry.py:_apply_replay_config_to_args()`，确保 replay 会恢复 `append_negative_prompt` 与 `ksampler_node_id`。不要改变当前 strict retry 校验的 `prompt_hash` / `seed` / `workflow_hash` 语义。
  **Must NOT do**: 不要要求旧 run.json 必须补齐新字段；不要借机扩大 replay 的行为范围到新建网站/数据库逻辑。

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: 涉及向后兼容、严格解析、namespace 桥接与 retry 一致性。
  - Skills: `[]` - 现有 dataclass + parser 模式足够。
  - Omitted: `['git-master']` - 非 git 任务。

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 6, 7 | Blocked By: 2, 3, 4

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `scripts/generation/run_replay.py:33` - 当前 replay 配置 dataclass 结构。
  - Pattern: `scripts/generation/run_replay.py:45` - 当前 `run.json` 严格读取入口。
  - Pattern: `scripts/generation/runner_retry.py:9` - 当前 replay 到 argparse namespace 的桥接。
  - Pattern: `scripts/generation/comfyui_part1_generate.py:410` - retry 流程使用 replay 配置的主路径。
  - Pattern: `tests/test_run_replay.py:49` - happy path fixture 基线。
  - Pattern: `tests/test_retry_incomplete_integration.py` - retry 集成路径必须继续工作。

  **Acceptance Criteria** (agent-executable only):
  - [ ] `uv run pytest -q tests/test_run_replay.py tests/test_retry_incomplete_integration.py tests/test_idempotent_retry_failed.py` 通过。
  - [ ] 旧 `run.json` fixture 不需要新增字段也能 replay。
  - [ ] 新 `run.json` 的 `append_negative_prompt` 与 `ksampler_node_id` 会被 replay 写回 namespace。

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: 旧 run.json 继续可 replay
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_run_replay.py -k legacy`
    Expected: 退出码 0；旧 fixture 不要求 `config_snapshot` 或 `model`
    Evidence: .sisyphus/evidence/task-5-replay-legacy.txt

  Scenario: 新 run.json 的新增字段会回放到 args
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_run_replay.py tests/test_retry_incomplete_integration.py -k "append_negative_prompt or ksampler"`
    Expected: 退出码 0；测试断言 retry/replay 后 `args.append_negative_prompt`、`args.ksampler_node_id` 正确恢复
    Evidence: .sisyphus/evidence/task-5-replay-new.txt
  ```

  **Commit**: NO | Message: `fix(generation): 兼容新旧 run.json 的 replay 与 retry` | Files: `scripts/generation/run_replay.py`, `scripts/generation/runner_retry.py`, `tests/test_run_replay.py`, `tests/test_retry_incomplete_integration.py`, `tests/test_idempotent_retry_failed.py`

- [x] 6. 将 negative prompt 追加与生图覆盖参数彻底迁移到 config 驱动

  **What to do**: 在生成执行链路中新增 `args.append_negative_prompt`，并让 `scripts/generation/runner_records.py`、`scripts/generation/comfyui_part1_generate.py`、相关 helper 全部改为使用 namespace/config 值，而不是 `COMFYUI_APPEND_NEGATIVE_PROMPT`。保持现有业务规则：仅当 `x_info_type == "normal"` 时拼接 append negative prompt；其他类型保持 base negative prompt。`generation_overrides` 与 `config_snapshot.generation` 必须都包含 `append_negative_prompt`；`metadata.jsonl` 的 `generation_params["negative_prompt"]` 继续记录最终生效字符串。deprecated env 路径只负责报错，不再参与结果计算。
  **Must NOT do**: 不要改变 `x_info_type` 判定规则；不要把最终拼接逻辑挪到 CLI 菜单层。

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: 逻辑分散在记录层、运行层、测试层，且结果可观测性要求高。
  - Skills: `[]` - 现有纯函数与 runner 模式足够。
  - Omitted: `['frontend-design']` - 非前端任务。

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 7 | Blocked By: 2, 3, 5

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `scripts/generation/runner_records.py:120` - 当前 effective generation params 组装位置。
  - Pattern: `scripts/generation/runner_records.py:162` - 当前按 `x_info_type` 追加 negative prompt 的逻辑入口。
  - Pattern: `scripts/generation/runner_env.py:69` - 当前 env append negative prompt 的解析逻辑，需要迁移出业务主路径。
  - Pattern: `tests/test_negative_prompt_append.py` - 现有 append 行为与 normal/non-normal 规则测试基线。
  - Pattern: `tests/test_runner_dry_run.py:213` - 当前 dry-run 对 append negative prompt 的集成断言。

  **Acceptance Criteria** (agent-executable only):
  - [ ] `uv run pytest -q tests/test_negative_prompt_append.py tests/test_runner_dry_run.py` 通过。
  - [ ] `metadata.jsonl` 中的 `generation_params.negative_prompt` 对 normal 类型体现 base + append 结果；非 normal 类型不追加。
  - [ ] 设置 `COMFYUI_APPEND_NEGATIVE_PROMPT` 不再改变使用 `--config` fresh run 的输出。

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: config 中的 append_negative_prompt 正常生效
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_negative_prompt_append.py tests/test_runner_dry_run.py -k "append_negative_prompt or normal"`
    Expected: 退出码 0；normal 类型记录最终 negative prompt，非 normal 类型保持不追加
    Evidence: .sisyphus/evidence/task-6-negative-prompt.txt

  Scenario: env 不再偷偷影响 config 驱动结果
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_runner_config.py tests/test_runner_dry_run.py -k "deprecated_env or append_env_ignored"`
    Expected: 退出码 0；测试断言 fresh run 下 env 不会改变结果或会直接报错
    Evidence: .sisyphus/evidence/task-6-negative-prompt-env.txt
  ```

  **Commit**: NO | Message: `refactor(generation): 将 negative prompt 追加迁入 YAML 配置` | Files: `scripts/generation/runner_records.py`, `scripts/generation/comfyui_part1_generate.py`, `scripts/generation/runner_env.py`, `tests/test_negative_prompt_append.py`, `tests/test_runner_dry_run.py`

- [x] 7. 收口下游兼容、示例配置与全量回归

  **What to do**: 补齐不直接属于生成主链、但会被本次改动波及的内容。新增一个可运行的示例配置文件，固定路径为 `data/runs/example.yaml`，内容必须展示完整 schema、引用现有 prompt/workflow 资产，并包含模型展示元数据；该文件既是未来手工编辑模板，也是测试可复用 fixture。同时在实现中把“推荐存放位置”统一写死为 `data/runs/`，作为 git-tracked 输入资产目录，而不是运行输出目录。更新 `.env.example`，只保留 5 个 runtime env，并标明 fresh run 业务参数改由 `--config` 提供。检查 `scripts/r2_upload/upload_io.py`、`scripts/r2_upload/upload_discovery.py`、`scripts/r2_upload/upload_planner.py`、`scripts/r2_upload/supabase_writer.py` 是否需要最小兼容调整；若无需改实现，也必须补测试证明扩展后的 `run.json` 不会破坏上传链路。
  **Must NOT do**: 不要新增网站页面或数据库表；不要让示例 config 偏离最终 schema。

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: 涉及跨目录兼容收口与最终回归。
  - Skills: `[]` - 主要是合约与示例资产管理。
  - Omitted: `['writing']` - 本任务重点是示例与兼容，不是纯文档写作。

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: Final Verification | Blocked By: 4, 5, 6

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `scripts/r2_upload/upload_io.py:33` - 上传链路读取 `run.json` 的入口。
  - Pattern: `scripts/r2_upload/upload_discovery.py:63` - 上传链路对 `run_dir` 名称的依赖。
  - Pattern: `scripts/r2_upload/upload_planner.py:388` - 上传计划中透传 `run_json` 的位置。
  - Pattern: `scripts/r2_upload/supabase_writer.py:254` - `run_json` 整体写入数据库载荷的位置。
  - Pattern: `data/prompts/X/common_prompts.yaml:1` - 示例 config 的 X prompt 引用目标。
  - Pattern: `data/prompts/Y/300_NAI_Styles_Table-test.yaml:1` - 示例 config 的 Y prompt 引用目标。
  - Pattern: `tests/test_r2_upload_cli_contract.py` - 上传 CLI 契约基线。
  - Pattern: `tests/test_r2_upload_cli_dry_run.py` - 上传 dry-run 契约基线。

  **Acceptance Criteria** (agent-executable only):
  - [ ] `data/runs/example.yaml` 可被测试成功加载。
  - [ ] `uv run pytest -q tests/test_r2_upload_cli_contract.py tests/test_r2_upload_cli_dry_run.py` 通过。
  - [ ] `.env.example` 只保留 5 个 runtime env，并明确 `--config` 是 fresh run 必填入口。
  - [ ] 全量目标回归命令全部通过。

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: 示例 config 可加载并跑通 dry-run 契约
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_runner_config.py tests/test_runner_dry_run.py -k "example_model or dry_run"`
    Expected: 退出码 0；示例 config 能被加载，并产出符合新旧契约的 run.json
    Evidence: .sisyphus/evidence/task-7-example-config.txt

  Scenario: 扩展后的 run.json 不破坏 R2 上传链路
    Tool: Bash
    Steps: 运行 `uv run pytest -q tests/test_r2_upload_cli_contract.py tests/test_r2_upload_cli_dry_run.py`
    Expected: 退出码 0；上传 CLI/dry-run 不因 run.json 新字段失败
    Evidence: .sisyphus/evidence/task-7-r2-compat.txt
  ```

  **Commit**: NO | Message: `chore(generation): 补齐示例配置与下游兼容回归` | Files: `data/runs/example.yaml`, `.env.example`, `scripts/r2_upload/upload_io.py`, `scripts/r2_upload/upload_discovery.py`, `scripts/r2_upload/upload_planner.py`, `scripts/r2_upload/supabase_writer.py`, `tests/test_r2_upload_cli_contract.py`, `tests/test_r2_upload_cli_dry_run.py`

## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [x] F1. Plan Compliance Audit - oracle
- [x] F2. Code Quality Review - unspecified-high
- [x] F3. Real Manual QA - unspecified-high (+ playwright if UI)
- [x] F4. Scope Fidelity Check - deep

## Commit Strategy
- 单主提交，完成后提交：`feat(generation): 支持基于 YAML 的运行配置`
- 若 TDD 过程中需要中间保存，可先用临时本地提交，但最终合并为单一功能提交。

## Success Criteria
- Fresh run 的业务参数来源唯一：`--config` 指向的 YAML。
- Replay/retry 对旧 run 与新 run 都可工作。
- `run.json` 兼具 reproducibility 与未来网站展示所需的紧凑元数据。
- 运行环境层仅剩约定好的 5 个 `COMFYUI_*` 变量。
- pytest 回归通过且无人工检查步骤。
