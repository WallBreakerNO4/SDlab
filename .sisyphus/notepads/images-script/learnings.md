### 任务 8: 更新首页 runs 列表 UI
- 更新了 `app/page.tsx` 的空态文案，从 "暂无 run.json" 改为更通用的 "暂无可用 runs，请确认数据源已配置。"
- 统一了 `RunSummary` 类型定义，从 `lib/comfyui-types.ts` 导入。
- 强化了 `isRunSummary` 类型检查，增加了 `run_id` 校验。
- 确保了在 API 返回错误或空数据时，页面能正确显示错误状态或空状态而不崩溃。
