<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-06 | Updated: 2026-09-04 -->

# scripts/cli/ — 交互菜单与入口注册

## 概览

- 该目录负责“脚本选择与执行入口”：菜单展示、输入读取、入口点加载、异常守卫。菜单覆盖生图（ComfyUI / NovelAI）、X/Y CSV→YAML、Y tag Danbooru 标注、上传到 R2、清空 R2 桶、删除 Run。

## 去哪儿改

| 任务          | 位置          | 备注                                                         |
| ------------- | ------------- | ------------------------------------------------------------ |
| 菜单文案/流程 | `menu.py`     | 菜单渲染、二次确认、执行结果提示；NovelAI 入口支持 --retry-failed / --retry-incomplete / --retry-error-code 恢复选项 |
| 可选脚本注册  | `registry.py` | `MenuEntry` 列表与 `entrypoint` 映射（ComfyUI/NovelAI 生图、转换/标注、上传/清桶/删除 Run） |
| 终端 I/O 抽象 | `io.py`       | 交互判定（TTY）与输入输出封装                                |

## 约定（本目录特有）

- 菜单层只做分发，不复制 `scripts/generation/` 或 `scripts/r2_upload/` 的业务实现
- 上传菜单先选择普通上传或强制重新发布；强制模式只向上传入口传递 `-F`，发布判定仍由 `scripts/r2_upload/` 负责
- NovelAI 生图菜单只枚举 `backend=novelai` 的 v2 配置；retry 恢复选项由菜单拼装 argv，业务判定仍在 `scripts/generation/novelai_generate.py`
- 执行入口必须通过 `entrypoint` 动态加载，保持主入口可测试
- 处理 `EOFError`/`KeyboardInterrupt` 时返回明确退出码，不抛裸异常到用户界面

## 反模式

- 不要在菜单层直接读写 `run.json` 或 `metadata.jsonl`
- 不要在这里引入外部上传凭证逻辑（属于 `scripts/r2_upload/` 边界）
