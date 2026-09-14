# 契约常量镜像用一致性守卫保持同步

> 状态：accepted

run key 正则、style_key 形态与 y_index 0-based 约定分散在 Python（生图 / 回填）、TypeScript（Web 校验）与 SQL（migration 内的 CHECK 与 RPC）三侧，任一处单独修改都会在另一侧运行时才暴露（ADR 0004 已把该风险记为 #6）。决定用跨语言一致性守卫保持镜像同步：Python 与 TypeScript 各用自己原生的正则与 type guard 跑同一份接受 / 拒绝行为样本，同时把副本文本钉到同一范式；SQL 侧从 migration 文本提取模式与上限，在样本上做等价平移验证。不引入单一来源或代码生成。

## Considered Options

- 单一来源（共享常量文件，三侧运行时读取）：拒绝。SQL migration 按时间戳顺序应用，已提交文件禁止回改，数据库无法在运行时读取仓库文件；强行让 migration 引用共享源会把它变成生成产物，破坏历史可审计性。
- 代码生成（由规范源生成 Python / TypeScript / SQL 常量）：拒绝。已应用的 migration 不能重新生成，只对未来副本生效，等于在守卫之外再维护一套机制。
- 一致性守卫：采纳。每个运行时验证自身语义，文本范式比对覆盖 SQL 这类无法在测试中执行的副本；共享样本让“什么算合法值”只有一个定义，守卫在 `pnpm test` 与 `uv run pytest` 中都会失败。

## Consequences

- 修改 run key / style_key / y_index 或相关上限（style_key 200、label 1000、对比 slice 40/12、run_dir 200）时，必须同步三侧并更新 `tests/fixtures/contract-constants.json`；只改一侧会被守卫拦住。
- 守卫在测试时生效；仓库没有 CI，依赖提交前运行 `pnpm test` 与 `uv run pytest`。
- 已被 `20260526_remove_favorites.sql` 删除的旧表约束（style_key 512 / label 4000）不属于现行契约，守卫只锁定现行约束名与 RPC 边界。
- y_index 不只是一个常量：生产侧锁 0-based 位置语义（含子集选择与重放），消费侧锁 SQL CHECK 与 Web guard 拒绝负数。
