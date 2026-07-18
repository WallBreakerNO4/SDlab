# Plan: 画师提示词收藏（Style Favorites）

> 对应 spec：`tasks/spec-style-favorites.md`（已评审） | 日期：2026-07-17

## 组件与依赖

```
T1 DB migration ──┬── T2 Python writer（supabase_writer 写 run_style_items）
                  ├── T3 回填脚本（确定性重放 run.json + Y 资产 → run_style_items）
                  └── T4 共享类型 + style-items API ── T5 收藏 API
                                                          │
                                              T6 客户端 hook（use-style-favorites）
                                                          │
                                              T7 行标签星标 ── T8 工具栏收藏面板
                                                          │
                                              T9 收藏页 ── T10 头部入口
                                                          │
                                              T11 e2e ── T12 文档与终验
```

- T1 是所有后续任务的前置（本地 `supabase db reset` 后各任务可独立验证）。
- T2 / T3 / T4 互不依赖，可并行；T5 依赖 T4 的共享类型。
- T7 / T8 同改 `virtual-grid.tsx` 周边，必须串行。
- T9 与 T7/T8 无文件冲突，可与 T8 并行，但默认顺序执行。

## 关键实现决策

1. **run_id 解析**：T2 中 `supabase_writer.py` 写 grid_items 时已解析 run 主键，复用该路径写 `run_style_items`；`label` 取 metadata 的 `y_value` 整串，`y_index` 保持 0-based（与 metadata.jsonl 一致）。
2. **0-based / 1-based 边界**：`run_style_items.y_index`、style-items API、网格内部一律 0-based；仅 T9 收藏页拼跳转 URL 时 `#{y_index + 1}`（hash 机制是 1-based 行号）。
3. **runs 表 name 字段**：T5 的 join 需要模型显示名；以 `lib/model-metadata.ts` 实际查询的列名为准（实施时确认，不猜）。
4. **缺失容忍与重放**：writer 对无 `y_style_key` 的 payload 跳过不报错、不阻断上传（已核实该字段平铺在 `image_payload` 顶层，`upload_planner.py:1544`）。回填脚本不依赖 `y_style_key`，也不用 `read_y_rows` 重放（它硬校验 `prompt-y-table/v3`，老资产是 v2）：改为 `yaml.safe_load` 最小解析 `items[].info.index` + 顶层 `collection_id`；`y_index` 即 YAML items 原始索引（`runner_coordinator.py:232`），映射为 `items[y_index].info.index → style_key`，并用 `run.json` 的 `selection.y_indexes` 做集合校验。
5. **style-items 拉取时机**：网格在「用户已登录 且 bootstrap ready」后惰性拉取；失败静默降级（星标隐藏），不重试风暴、不阻塞网格。
6. **收藏页是用户私有页**：`generateMetadata` 在 `buildSeoMetadata()` 之上加 `robots: { index: false }`（若工具函数不支持则直接合并 metadata 返回）。
7. **头部入口**：登录后在 `components/site-header.tsx` 的 nav（"Prompt 法典" 链接旁）显示收藏页链接；未登录不渲染。
8. **面板内容**：所有模型生图均使用同一 Y 资产 `data/prompts/Y/300_NAI_Styles_Table.yaml`（432 项全量选择，用户确认无例外），收藏串必然存在于当前 run 且 `y_index + 1` 恒等于网格行号——面板按行号升序列出全部收藏、全部可跳，不做"包含 N/M"区分（仅保留防御性过滤）；面板 label 取当前 run 网格行标签（客户端 join），收藏页按收藏时间倒序、用快照 label。
9. **middleware 白名单**：`LOCALIZED_PATH_PATTERNS` 需加 `/^\/favorites/`，否则无前缀 `/favorites` 不会被重定向（带前缀的 `/zh|en/favorites` 经 `LOCALE_PREFIX_RE` 本就放行）。
10. **hook 归属**：`hooks/AGENTS.md` 禁止页面级业务数据 hook，故共享类型与薄 fetch/mutate 函数放 `lib/style-favorites.ts`，网格 stateful hook 放 `app/models/[runDir]/use-style-favorites.ts`（与被撤旧实现同位置），收藏页组件自包含拉取。
11. **模型显示名**：`runs` 表无 name 列；显示名取 `run_list_items.model_name`（`lib/model-metadata.ts` 同款），`run_style_items` 按投影表惯例冗余 `run_dir` 后直接按 `run_dir` 关联。
12. **发布顺序**：远端 migration 推送 → 生产回填（service role，用户主导执行）→ web 部署。回填耗时短（6 run × 432 行），空窗期不做特殊处理。
13. **style-items 不加缓存（MVP）**：主键索引查询 + ~20-30KB + 模型个位数，直接接受每详情页 +1~2 个请求；后续有性能数据再补 `unstable_cache`。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| Y 资产版本漂移（老 run 用 v2 版 YAML，hash `08eacc43` vs 当前 v3 `0220d6c7`；`read_y_rows` 硬校验 v3 无法重放） | 回填不走 loader，`yaml.safe_load` 最小解析 `info.index`；按 `y_json_sha256` 从 git 历史取版本（已验证可找回：`318b983a`）；找不到则跳过该 run 并报错 |
| 同一 run_dir 有多个本地产物目录（`outputs/<run>` 与 `outputs/<run>_old`） | 优先精确目录名匹配；重放后做条目数校验，`--dry-run` 输出供人工核对再落库 |
| e2e 已登录态获取（无本地 Supabase） | service-role admin 链路 + 应用自身 PKCE 回调建真实 session（spec 决策 13）；T11 先 spike 验证 generateLink 不被远端 `email:false` 阻断，失败则降级为未登录路径 e2e + curl 验已登录 API |
| Mixer 行标签已有两个复制按钮，空间紧张 | 星标放 section 行内右侧小图标；实施时截图人工核对，必要时只缩小间距不改布局结构 |
| 历史 run 未回填时收藏页显示「无可用模型」 | 属预期行为，UI 文案明示；回填脚本可随时补 |
| 远端 migration 同步 | 属 spec「Ask first」边界：本地验证后由用户决定何时推远端 |
| 旧撤回功能残留（`tests/test_supabase_writer.py:159` 死引用） | T2 顺手清理，不扩散 |

## 验证检查点

- **CP1**（T1 后）：本地无 Supabase 栈（用户确认全部在远端），改用一次性 Postgres 容器按序应用全部 migrations 验证：两表 + policies + grants 存在、迁移链干净通过、重复执行幂等；远端推送后由用户复核。
- **CP2**（T3 后）：`uv run pytest -q` 全绿。
- **CP3**（T5 后）：dev server curl —— 未登录 401、坏 body 400、PUT→GET→DELETE 闭环正确、GET 的 runs join 形态正确。
- **CP4**（T10 后）：浏览器手工主流程：登录 → mixer run 收藏一行 → 普通 run 收藏一行 → 面板跳转 → 收藏页看到两条 → 跨模型跳转落点正确 → 取消收藏生效。
- **CP5**（T12）：`pnpm lint` + `uv run pytest -q` + e2e 全绿。
