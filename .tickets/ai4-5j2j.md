---
id: ai4-5j2j
status: open
deps: [ai4-9hcj]
links: []
created: 2026-10-17T15:21:48Z
type: task
priority: 2
assignee: SciWeave
parent: ai4-ru15
tags: [wayfinder:task, terminusdb, reproducibility, dependencies, ai4science]
---
# 固定 TerminusDB 验证服务版本并同步说明

根据 ai4-9hcj 已验证的 TerminusDB 12.0.8 与 TerminusDB Store 0.19.8，将本地 Compose 从 latest 改为可复现的明确镜像版本，并同步 dockers/service/terminusdb/README.md、docs/DEPENDENCIES.md 与 humans/dev/DEPENDENCIES.md 的版本、来源、启动和验证说明。此任务只处理实现准备与文档一致性，不把 TerminusDB 选择伪装成已确定的正式产品架构。

## Design

固定镜像 tag 必须与已验证行为一致；说明默认凭据只用于本地验证且不得提交；保留服务端口、数据卷和启动命令；权威依赖文档先改，再同步面向人副本；检查 compose、README、依赖清单和 ai4-9hcj 的事实一致。

## Acceptance Criteria

compose.yaml 不再使用 latest；README 明确固定版本、端口、数据卷、启动/停止和凭据要求；docs/DEPENDENCIES.md 记录 TerminusDB 版本、来源、用途、许可证或限制、安装/验证命令；humans/dev/DEPENDENCIES.md 与权威文档一致；ai4-9hcj 回写提交和验证结果；git diff --check 通过；不新增业务代码或未确认运行时依赖。
