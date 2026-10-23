---
name: deploy-task-agent-troubleshoot
description: 按边界排查 Task Agent 配置和服务问题。
---

# 排障

先阅读 `references/failure-matrix.md`，按顺序检查配置、假链路和用户服务。Personal Agent 只能修正 Agent 定义、工作流、资源和环境变量；runtime、Worker Lease、Gateway 或 systemd 行为问题应交给套件维护者。

检查 hook 时确认 harness 打开会补启动缺失的用户服务，关闭 harness 不会停止常驻服务。