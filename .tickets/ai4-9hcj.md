---
id: ai4-9hcj
status: closed
deps: []
links: []
created: 2026-10-16T03:23:05Z
type: task
priority: 1
assignee: qiyueran
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

**2026-10-16T04:16:17Z**

## Validation results

实测容器镜像实际版本为 TerminusDB 12.0.8，TerminusDB Store 0.19.8；服务端口 6363。未设置 TERMINUSDB_ADMIN_PASS 时，容器初始化脚本默认管理员密码为 root；匿名访问可以读取 /api/ 和 /api/info，但不能创建数据库。使用本地测试凭据 admin:root 完成验证，未写入仓库。

已验证：
- 可以创建数据库，并生成 initial schema Commit。
- 使用原生命令创建 Schema Class：TaskNode、DependencyEdge。
- 通过 HTTP POST /api/document/{org}/{db} 写入 TaskNode，提交 author/message 后立即生成 ValidCommit。
- 可以通过 HTTP 更新 TaskNode；每次写入都生成新的 Commit，并记录 author、message、parent、timestamp。
- 可以通过 HTTP 写入 DependencyEdge，Schema 引用 TaskNode 可用。
- /api/log 和 terminusdb log 可以读取提交链；terminusdb history 可以读取指定节点历史；terminusdb diff 可以比较两个提交中的节点差异。
- terminusdb reset 可以把正式分支指针恢复到旧 Commit；恢复后当前 log 和节点内容回到旧状态，新 Commit 不再出现在该分支的 log 中。因此 reset 是移动分支状态，不等价于“创建新的恢复 Commit”，平台若要求不可擦除审计，需要在 reset 前保存目标和原提交，并由平台追加 Trace/Proposal。
- HTTP 写入附带 commit=false 仍然生成 ValidCommit，当前 API 没有提供可用的未提交工作区语义。

尚未确认：HTTP/CLI 创建候选分支的正确参数和分支工作区行为；多次 branch create 尝试均未成功，错误显示参数被解析为 main 或远程仓库路径。该问题另建后续验证票。

初步判断：TerminusDB 可以承担 Mapping 的 Schema、TaskNode、DependencyEdge、Commit、History 和 Diff 存储；Agent 可以通过 MCP 封装 HTTP 文档提交，但每次提交会直接产生 Commit，因此“草稿/待审核变更”必须由平台侧 Proposal 状态或独立候选数据库/分支承载。原生 reset 不满足不可变审计要求，回滚策略需要平台补充保护。
