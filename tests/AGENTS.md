# tests/ — pytest 约定

## 概览

- 测试偏“可观测输出”：验证文件是否生成、JSON 字段合约、结构化错误；fixture 以 `tmp_path`/`monkeypatch`/`capsys` 为主。

## 去哪儿看

| 场景 | 位置 | 备注 |
| --- | --- | --- |
| 顶层入口行为（help/exit code/dry-run 落盘） | `tests/test_main_entrypoint.py` | 直接调用 `main.main()` |
| runner：dry-run / env 读取 / resume / 不触发 ComfyUI | `tests/test_runner_dry_run.py` | 临时目录写 CSV + `.env` + 断言 `run.json`/`metadata.jsonl` |
| prompt 纯函数（normalize/hash/seed/render） | `tests/test_prompt_grid.py` | 无网络/无文件依赖 |
| workflow patch（引用追溯/overrides/异常） | `tests/test_workflow_patch.py` | `pytest.raises` 覆盖非法输入 |
| ComfyUI client（HTTP/WS helpers + 错误码） | `tests/test_comfyui_client.py` | `monkeypatch` + fake response/ws；含 `parametrize` |
| 依赖烟雾导入 | `tests/test_smoke.py` | 最轻量的集成信号 |

## 约定（本目录特有）

- 断言优先围绕合约：`run.json` 字段、`metadata.jsonl` 逐行 JSON、状态码与错误码（而不是“跑通就行”）
- mock 方式：优先 `monkeypatch.setattr(...)` 替换网络/WS；避免引入额外依赖
- pyright：测试文件可能用文件级 `# pyright:` 放宽 unknown 类型（主要因为 fake/mocks）

## 运行

- 测试命令清单在根 `AGENTS.md`（`uv run pytest -q` / 单文件 / `::` / `-k`）。
