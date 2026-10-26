---
id: ai4-t5f8
status: in_progress
deps: []
links: []
created: 2026-10-21T08:15:45Z
type: chore
priority: 2
assignee: hanjiang
tags: [enhancement, ready-for-agent]
---
# 配置项目内 Pi 开发容器

将现有本地 Pi 配置和 Docker 构建脚本收敛为可复现、无真实凭据、面向 AI4Sci 仓库的开发环境。

## Design

使用项目级 .pi/agent/models.json 声明模型目录，真实 API 密钥仅由未提交 .pi/.env 注入；Docker Compose 挂载仓库并以宿主 UID/GID 运行；移除交易依赖和未声明的自动安装扩展。

## Acceptance Criteria

仓库提交 Pi 模型示例与环境变量示例，不包含真实密钥；Docker 镜像可构建并可在仓库根目录启动 Pi；容器默认工作目录为仓库根目录，且不以 root 写入挂载目录；文档说明本机和容器两种启动方式及验证命令；配置语法可由 Pi 验证。


## Notes

**2026-10-21T08:17:18Z**

AI 生成的实施记录：已确认现有 .pi/.env 含真实 DeepSeek API Key，必须在提供商后台撤销。实施将仅保留环境变量示例，不记录或回显任何真实凭据。依赖调整：容器使用 Node.js 24、Pi Coding Agent 和可选 Python/uv；许可证与准确版本将在锁定包元数据后回写。

**2026-10-25 转交（hanjiang）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。转交原因：Frank Qi 暂时无法继续推进项目，经其本人授权，由 hanjiang 接手本票后续推进与收口。原负责人 Frank Qi，转交时间 2026-10-25T12:41:00Z。转交只变更归属与记录，不改写正文与验收标准。
