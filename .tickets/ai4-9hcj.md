---
id: ai4-9hcj
status: open
deps: []
links: []
created: 2026-10-16T03:23:05Z
type: task
priority: 1
assignee: SciWeave
parent: ai4-ru15
tags: [wayfinder:prototype, terminusdb, mapping, ai4science]
---
# TerminusDB Mapping 版本与 Agent 提交原型验证

## Question
验证 TerminusDB 是否能以最少自定义版本逻辑支持本项目的核心流程：Agent 通过标准 MCP 提交创建和更新 TaskNode、提交失败报告、提出新增节点和申请回滚；中央 Agent 生成结构差异并预审；负责人批准后形成正式 Commit；系统可以查看历史、比较差异并通过新 Commit 恢复旧节点。重点确认 TerminusDB 对草稿/未提交状态、分支、Commit、Diff、Merge 或恢复的实际行为。

## Acceptance Criteria

完成一个最小可运行原型或验证记录；明确 TerminusDB 支持和不支持的操作；给出 Agent 提交、中央 Agent 预审、负责人批准、正式 Commit 和回滚流程；记录安装、运行和验证命令；据此确定后续是否保留 TerminusDB 或增加平台适配层。

## Notes

**2026-10-16T03:41:02Z**

已添加本地 TerminusDB Compose 配置：dockers/service/terminusdb/compose.yaml，以及手动启动、查看日志、停止和清理说明：dockers/service/terminusdb/README.md。配置使用 terminusdb/terminusdb-server:latest、6363 端口和 ai4sci-terminusdb-data 持久化卷；未执行 Docker 命令，未提交真实凭据。首次验证后需要根据实际镜像行为固定版本 tag，并回写验证结果。
