# scripts/r2_upload/ — R2 上传边界

## 概览

- 本目录用于承载图片上传到 R2 的集成逻辑；当前入口仍是未实现占位。

## 去哪儿改

| 任务 | 位置 | 备注 |
| --- | --- | --- |
| 上传脚本入口 | `scripts/r2_upload/upload_images_to_r2.py` | 目前 `NotImplementedError`，后续在此扩展 |

## 约定（本目录特有）

- 上传逻辑与生图逻辑分层：不要反向耦合到 `scripts/generation/` 内部流程。
- 凭证输入优先走环境变量/参数，不在仓库内落盘明文配置。
- 错误处理需区分：参数错误、认证失败、网络失败、远端限流/重试耗尽。

## 反模式

- 不要把真实凭证文件或密钥内容提交到仓库（包含 `.env*` 与任何私有配置）。
- 不要把 bucket/key/endpoint 等敏感细节写入异常 message 或日志。
- 不要把上传结果写回 `data/`；运行产物仍归 `comfyui_api_outputs/`。
