# scripts/cli/ — 交互菜单与入口注册

## 概览

- 该目录负责“脚本选择与执行入口”：菜单展示、输入读取、入口点加载、异常守卫。

## 去哪儿改

| 任务 | 位置 | 备注 |
| --- | --- | --- |
| 菜单文案/流程 | `scripts/cli/menu.py` | 菜单渲染、二次确认、执行结果提示 |
| 可选脚本注册 | `scripts/cli/registry.py` | `MenuEntry` 列表与 `entrypoint` 映射 |
| 终端 I/O 抽象 | `scripts/cli/io.py` | 交互判定（TTY）与输入输出封装 |

## 约定（本目录特有）

- 菜单层只做分发，不复制 `scripts/generation/` 的业务实现。
- 执行入口必须通过 `entrypoint` 动态加载，保持主入口可测试。
- 处理 `EOFError`/`KeyboardInterrupt` 时返回明确退出码，不抛裸异常到用户界面。

## 反模式

- 不要在菜单层直接读写 `run.json` 或 `metadata.jsonl`。
- 不要在这里引入外部上传凭证逻辑（属于 `scripts/r2_upload/` 边界）。
