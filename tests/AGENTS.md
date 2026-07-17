<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-07-16 -->

# tests/ — pytest 约定

## 概览

- 测试覆盖 generation runner、YAML 配置加载、R2 上传、CLI 菜单、资产转换、重试机制与合约校验。偏“可观测输出”：验证文件生成、YAML/JSON 字段合约、结构化错误。

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
| CLI 菜单                      | `test_main_menu_*.py`（6 个）                                      | 菜单触发/循环/边界                                  |
| CSV→YAML 转换                 | `test_convert_x_csv_to_json.py`                                    | X prompt 资产转换与描述字段                         |
| 清桶入口                      | `test_r2_clear_bucket.py`                                          | clear bucket 菜单/环境变量分支                      |
| 导出合约                      | `test_public_exports_contract.py`                                  | `__all__` 检查                                      |
| 依赖烟雾                      | `test_smoke.py`                                                    | 最轻量集成信号                                      |
| prompt 资产                   | `test_prompt_assets.py`                                            | data/ 下 YAML 资产有效性                            |
| negative prompt               | `test_negative_prompt_append.py`                                   | 负面提示词拼接                                      |
| 重试失败项幂等性        | `test_idempotent_retry_failed.py`                         | 验证重复重试不重复生成 |
| NovelAI 生图入口        | `test_novelai_generate.py`                                | NovelAI 生图 argparse + 流程测试 |
| 历史 run 回填           | `test_backfill_run_style_items.py`                        | Y 资产 sha256 重放/git stub、集合校验、幂等 upsert、dry-run |

## 约定（本目录特有）

- 断言优先围绕合约：`run.json` 字段、`metadata.jsonl` 逐行 JSON、状态码与错误码
- mock 方式：优先 `monkeypatch.setattr(...)` 替换网络/WS；避免引入额外 mock 依赖
- pyright：测试文件可用文件级 `# pyright:` 放宽 unknown 类型（因 fake/mocks）
- 固定样例资产放在 `tests/fixtures/`；当前更多共享 setup 直接写在测试文件 helper 中，本仓库目前没有顶层 `conftest.py`

## 运行

- 命令清单在根 `AGENTS.md`（`uv run pytest -q` / 单文件 / `::` / `-k`）
- Artist Mixer 定向回归：`uv run pytest -q tests/test_prompt_grid.py tests/test_run_replay.py tests/test_runner_config.py tests/test_runner_dry_run.py tests/test_workflow_patch.py`
