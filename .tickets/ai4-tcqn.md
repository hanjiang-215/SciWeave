---
id: ai4-tcqn
status: open
deps: [ai4-h9ci]
links: []
created: 2026-10-29T14:26:58Z
type: feature
priority: 2
assignee: Frank Qi
tags: [toolkit, task-agent, migration, lifecycle, ready-for-agent]
---
# 迁移旧用户级安装并保留数据卸载

依据工具包项目级部署与 Harness 导出设计规格，提供旧 ~/.sciweave/task-agent 安装迁移、升级保留和默认数据保留卸载流程。

## Design

Blocked by Linux 项目绑定 Task Agent 服务生命周期。无法可靠判断旧安装归属时必须停止；升级先完成清单和路径校验；普通卸载移除服务、运行代码和生成输入但保留 data、project 与 .env。

## Acceptance Criteria

- [ ] 能识别旧安装及其项目绑定状态，展示将迁移的代码、状态、服务和配置。
- [ ] 迁移要求用户明确选择目标项目根，并支持迁移后重绑 systemd 实例。
- [ ] 无法可靠判断旧安装归属时停止并说明原因，不自动猜测。
- [ ] 升级保留项目定义、Workflow、本地资源、.env、SQLite、会话和日志；失败时保留旧可运行版本或给出恢复路径。
- [ ] 普通卸载默认保留 data、project 和 .env，删除运行数据必须是独立且明确确认的操作。
