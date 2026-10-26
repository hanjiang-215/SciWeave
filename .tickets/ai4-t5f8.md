---
id: ai4-t5f8
status: in_progress
deps: []
links: []
created: 2026-10-21T08:15:45Z
type: chore
priority: 2
assignee: hanjiang
tags: [enhancement, ready-for-human]
---
# 配置项目内 Pi 开发容器

将现有本地 Pi 配置和 Docker 构建脚本收敛为可复现、无真实凭据、面向 AI4Sci 仓库的开发环境。

## Design

使用项目级 .pi/agent/models.json 声明模型目录，真实 API 密钥仅由未提交 .pi/.env 注入；Docker Compose 挂载仓库并以宿主 UID/GID 运行；移除交易依赖和未声明的自动安装扩展。

## Acceptance Criteria

> 2026-10-27 范围修订：本节验收已废止，现行验收见「范围修订（2026-10-27）」；原文保留以便追溯。

仓库提交 Pi 模型示例与环境变量示例，不包含真实密钥；Docker 镜像可构建并可在仓库根目录启动 Pi；容器默认工作目录为仓库根目录，且不以 root 写入挂载目录；文档说明本机和容器两种启动方式及验证命令；配置语法可由 Pi 验证。

## 范围修订（2026-10-27）

原验收要求把 Pi 配置、镜像构建和文档作为项目交付物入库，与 `.cursor/rules/dev/pi.mdc`（`alwaysApply: true`，`f4d4889`，2026-10-21T16:32+08:00）及 `AGENTS.md` 的目录边界冲突。该规则晚于本票创建（16:15）和 AI 实施记录（16:17）提交，属维护者事后决策；经确认，规则优先。

现行验收：

1. 本票与 `pi.mdc` 的冲突及裁决依据已记录在票内。
2. 仓库不新增 Pi 配置、镜像构建文件或相关文档；跟踪历史中无 `.pi` / `pi-docker` 相关文件。
3. `.pi/.env` 中曾出现的 DeepSeek API Key 已在提供商后台撤销，撤销时间回填本票。

待办为第 3 条，回填后关闭本票。若后续确需项目内可复现的 Pi 环境，须先修改 `pi.mdc`。

## Notes

**2026-10-21T08:17:18Z**

AI 生成的实施记录：已确认现有 .pi/.env 含真实 DeepSeek API Key，必须在提供商后台撤销。实施将仅保留环境变量示例，不记录或回显任何真实凭据。依赖调整：容器使用 Node.js 24、Pi Coding Agent 和可选 Python/uv；许可证与准确版本将在锁定包元数据后回写。

**2026-10-25 转交（hanjiang）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。转交原因：Frank Qi 暂时无法继续推进项目，经其本人授权，由 hanjiang 接手本票后续推进与收口。原负责人 Frank Qi，转交时间 2026-10-25T12:41:00Z。转交只变更归属与记录，不改写正文与验收标准。

**2026-10-27 范围修订（hanjiang）**

身份核对：`assignee=hanjiang`、当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

裁决：按 `.cursor/rules/dev/pi.mdc` 与 `AGENTS.md` 的目录边界，Pi 开发环境只保留在本地 `.pi` / `pi-docker`，本票不产出仓库文件；原验收已标注废止，原文保留。

依据：`pi.mdc` 由 Frank Qi 于 2026-10-21T16:32+08:00 提交（`f4d4889`），晚于本票创建（16:15）与 AI 实施记录（16:17），是发现 `.pi/.env` 含真实密钥之后的明确决策。

现状：`.pi` / `pi-docker` 在本仓库和当前机器均不存在，`git log --all -- .pi` 无记录；原「现有本地配置」在转交前负责人机器上，已不可得。

下一步：hanjiang 在 DeepSeek 后台撤销泄漏的 Key，回填撤销时间后关闭本票；在此之前保持 `in_progress`。
