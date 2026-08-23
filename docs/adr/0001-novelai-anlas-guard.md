# NovelAI 后端一律拒绝 Anlas 计费请求（Anlas 守卫）

NovelAI Diffusion V5 为 Opus 订阅引入了会耗尽的可回充免费额度（电池），耗尽后请求不报错、直接静默转 Anlas 计费；而本仓库使用的账户 Anlas 余额极小（约一张 normal 档计费图的价格），一次误扣即清零。因此决定：NovelAI 生图链路在任何情况下都不发起会消耗 Anlas 的请求——参数合规校验（面积 ≤ 1024×1024、步数 ≤ 28、单张、纯 t2i）在客户端层对所有模型强制执行，V5 额外在每格生成前轮询 `/user/subscription` 的 `usage` 电量并在生成后核对 Anlas 余额。守卫触发时硬停（未完成网格单元记为带专属错误码的失败，不做任何等待或付费重试），由人工择机用 `--retry-failed --retry-error-code` 恢复。

## Considered Options

- 耗尽后挂起等待电量回充：拒绝。回充满格需约一周，挂起语义复杂且不可控。
- 提供 `--allow-anlas` 显式付费逃生门：拒绝。核心诉求就是杜绝扣费，留门徒增误触发面。
- 仅对 V5 挂守卫：拒绝。参数合规校验对 V4.5 同样防误配（如 steps 调到 30 会立刻被拦下），机制只有一份。

## Consequences

- 非 Opus 订阅的 API key 无法通过 NovelAI 后端生图（启动即中止），因为没有免费档可言。
- 402（余额不足）映射的 `AuthenticationError` 不再重试——它是终态错误，重试只会空转。
- NovelAI 入口此前接受了但从未实现 `--retry-failed/--retry-error-code`；守卫的人工恢复依赖它们，须一并实现。
