<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-09-04 -->

# tests/ — pytest + Node node:test 约定

## 概览

- Python 测试使用 pytest，覆盖 generation runner、NovelAI 链路、YAML 配置、R2 上传、CLI、资产转换和重试；TypeScript 测试使用 Node `node:test` + `tsx`，覆盖收藏 label、模型指南数据层、sitemap 条目与模型对比的边界/guard。整体偏“可观测输出”：验证文件生成、YAML/JSON 字段合约、结构化错误与边界上限。

## 去哪儿看

| 场景                          | 位置                                                               | 备注                                                |
| ----------------------------- | ------------------------------------------------------------------ | --------------------------------------------------- |
| 顶层入口行为                  | `test_main_entrypoint.py`                                          | help/exit code/dry-run 落盘                         |
| runner 配置加载               | `test_runner_config.py`                                            | `data/models/*/config.yaml` schema、repo-relative 路径、Mixer 限制 |
| runner dry-run / env / resume | `test_runner_dry_run.py`                                           | run.json/metadata.jsonl + Mixer 快照/`artist_chain` 合约     |
| runner WS 降级                | `test_runner_ws_fallback.py`                                       | WS 连接失败时的降级行为                             |
| prompt 纯函数                 | `test_prompt_grid.py`                                              | normalize/hash/seed/render + general/artists 拆分 |
| workflow patch                | `test_workflow_patch.py`                                           | CLIPTextEncode/Anima Artist Mixer 引用追溯与异常拓扑 |
| ComfyUI client                | `test_comfyui_client.py`                                           | HTTP/WS + 错误码；含 parametrize                    |
| 重试策略                      | `test_retry_attempt.py`/`test_retry_policy.py`                     | 重试决策与次数控制                                  |
| 重试失败项筛选                | `test_retry_failed_selection.py`/`test_retry_failed_errors.py`     | failed 项筛选逻辑                                   |
| 重试不完整集成                | `test_retry_incomplete_integration.py`                             | 端到端重试流程                                      |
| 运行回放                      | `test_run_replay.py`                                               | workflow 快照兼容、Mixer 回放、strict artist chain 校验 |
| R2 客户端                     | `test_r2_client.py`                                                | boto3 mock + 重试                                   |
| R2 变体/编码                  | `test_r2_variants.py`/`test_r2_encoding_params.py`                 | 变体规划 + 编码参数                                 |
| R2 keys/路径安全              | `test_r2_keys.py`/`test_r2_path_safety.py`                         | key 生成 + 路径校验                                 |
| R2 manifest                   | `test_r2_manifest.py`                                              | 上传清单生成                                        |
| R2 上传 CLI                   | `test_r2_upload_cli_contract.py`/`test_r2_upload_cli_dry_run.py`   | CLI 合约 + dry-run                                  |
| R2 幂等性                     | `test_r2_upload_idempotency.py`                                    | 重复上传幂等                                        |
| R2 本地 Supabase 集成         | `test_r2_upload_integration_local_supabase.py`                     | 需本地 Supabase                                     |
| Supabase writer               | `test_supabase_writer.py`/`test_supabase_writer_postgrest_http.py` | upsert + HTTP mock                                  |
| Mixer prompt parts 上传       | `test_r2_upload_mixer_prompt_parts.py`                             | 上传链路 Mixer prompt parts enrich/legacy 兼容      |
| CLI 菜单                      | `test_main_menu_*.py`（6 个）                                      | 菜单触发/循环/边界                                  |
| CSV→YAML 转换                 | `test_convert_x_csv_to_json.py`/`test_convert_y_csv_to_json.py`   | X/Y prompt 资产转换与描述字段                       |
| Y 标签类型标注                | `test_annotate_y_tag_types_from_danbooru.py`                       | Danbooru 标注脚本测试                               |
| 清桶入口                      | `test_r2_clear_bucket.py`                                          | clear bucket 菜单/环境变量分支                      |
| 导出合约                      | `test_public_exports_contract.py`                                  | `__all__` 检查                                      |
| 依赖烟雾                      | `test_smoke.py`                                                    | 最轻量集成信号                                      |
| prompt 资产                   | `test_prompt_assets.py`                                            | data/ 下 YAML 资产有效性                            |
| negative prompt               | `test_negative_prompt_append.py`                                   | 负面提示词拼接                                      |
| 重试失败项幂等性        | `test_idempotent_retry_failed.py`                         | 验证重复重试不重复生成 |
| NovelAI 生图入口        | `test_novelai_generate.py`                                | NovelAI 生图 argparse + 流程测试 |
| NovelAI Anlas 守卫      | `test_novelai_anlas_guard.py`                             | 免费资格参数校验、V5 电量预检、守卫错误码与 SDK 占位参数 |
| NovelAI 重试            | `test_novelai_retry.py`                                   | retry / retry-incomplete 回放与守卫码捞回 |
| 历史 run 回填           | `test_backfill_run_style_items.py`                        | Y 资产 sha256 重放/git stub、集合校验、幂等 upsert、dry-run |
| 画师串收藏 label        | `style-favorites.test.ts`                                 | 仅覆盖 `isStyleFavoriteLabel()` 的空白、1000 字符上限 |
| 模型对比部分合约        | `style-comparison.test.ts`、`comparison-matrix-utils.test.ts` | cursor、limit、slice body 边界、目录/详情 guard、viewer cookie、cache URL、BlurHash lookup |
| 无环境文件测试入口      | `env-file-path.test.ts`、`no-env-node-options.test.ts`     | Node 测试入口的路径与参数防护 |
| 模型指南数据层          | `model-guides.test.ts`                                    | `parseModelGuide()` frontmatter 契约、`buildGuideIndex()` / `resolveGuideLocale()` / `resolveGuidePath()` |
| 指南 sitemap 条目       | `sitemap.test.ts`                                         | `buildGuideSitemapEntries()` 只含实际存在语言 + hreflang alternates |
| 模型详情 response guard | `model-detail-types.test.ts`                              | `isModelDetailResponse()` 本地化描述字段校验 |
| 模型描述 Markdown URL   | `model-description-markdown.test.ts`                      | `transformModelDescriptionUrl()` 拒绝斜杠网络路径引用 |
| 对比 RPC 迁移防回归     | `style-comparison-rpc-migration.test.ts`                  | security-invoker RPC、grants、BlurHash RPC、EXPLAIN 验收脚本、模型缓存 300s 约束 |

## 约定（本目录特有）

- 断言优先围绕合约：`run.json` 字段、`metadata.jsonl` 逐行 JSON、状态码与错误码
- mock 方式：优先 `monkeypatch.setattr(...)` 替换网络/WS；避免引入额外 mock 依赖
- pyright：测试文件可用文件级 `# pyright:` 放宽 unknown 类型（因 fake/mocks）
- 固定样例资产放在 `tests/fixtures/`；共享 setup 写在测试文件 helper 中，没有顶层 `conftest.py`
- TypeScript 测试使用 `node:assert/strict` + `node:test`，通过 `pnpm test` 执行 `node --import tsx --test tests/*.test.ts`；不要混入 Playwright 浏览器断言。
- 模型对比单测未覆盖 slice response guard，也未覆盖 `mergeComparisonFavorites()`、`getVisibleModels()`、`reconcileHiddenRunDirs()`、`flattenRowSlides()`；修改这些逻辑时应补对应测试。
- 修改 placement / row 逻辑时，应增加或保持对 0-based `y_index` 结构的测试；单测不等同于 E2E。

## 运行

- Python：`uv run pytest -q`（支持单文件 / `::` / `-k`）
- TypeScript：`pnpm test`
- Artist Mixer 定向回归：`uv run pytest -q tests/test_prompt_grid.py tests/test_run_replay.py tests/test_runner_config.py tests/test_runner_dry_run.py tests/test_workflow_patch.py`
- NovelAI 定向回归：`uv run pytest -q tests/test_novelai_generate.py tests/test_novelai_anlas_guard.py tests/test_novelai_retry.py`
