---
id: ai4-0nuq
status: closed
deps: []
links: []
created: 2026-10-19T07:24:35Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-z3z4
tags: [implementation, gateway]
---
# Gateway 健康检查与 Owner Command 基础闭环

实现 Gateway 的第一条可验证垂直路径：本地 Python 项目入口、测试入口和依赖声明建立后，Owner 使用本地开发令牌提交一个带 task_node_id、命令内容和幂等键的请求，Gateway 将 TaskSession、OwnerCommand、ExecutionRecord 初始状态和命令接收审计写入 SQLite，并可通过公共 HTTP seam 查询执行状态和健康状态。首版不要求真实 Worker 执行；Runtime 可使用测试替身。

## Acceptance Criteria

- [ ] 建立可运行的 Python Gateway 项目入口和测试命令，并记录产品依赖、版本约束、来源和验证方式。
- [ ] 健康检查在存储可用时返回成功状态。
- [ ] 合法开发令牌可以提交 Owner Command 并得到 command_id、execution_id 和初始状态。
- [ ] Gateway 在一次事务中创建 TaskSession、OwnerCommand、ExecutionRecord 初始记录和 AuditEvent。
- [ ] 可以通过 HTTP 公共 seam 查询 execution_id 对应的状态、task_node_id 和 session_id。
- [ ] 未提供或提供错误令牌的请求被拒绝，真实凭据不进入仓库。


## Notes

**2026-10-19T08:01:03Z**

实现完成（2026-10-19）：在 sci-weave/gateway 建立 Python 标准库 Gateway MVP 基础闭环。提供 /health、Bearer 开发令牌保护的 POST /v1/commands 和 GET /v1/executions/{execution_id}；SQLite 同事务创建 TaskSession、OwnerCommand、ExecutionRecord 初始记录和 AuditEvent；幂等键重复提交返回原执行；补充 README、unittest 集成测试和 sci-weave 目录规则。未实现 Worker、fast-agent、MCP、Redpanda 或 A2A。验证：PYTHONPATH=sci-weave python3 -m unittest discover -s sci-weave/gateway/tests -v（3 passed）；python3 -m compileall -q sci-weave/gateway；git diff --check；ReadLints 无诊断。

**2026-10-19T08:04:24Z**

审查修复与提交：修复并发幂等检查的事务/锁边界，补充 JSON 对象校验，测试改为只通过 HTTP seam 验证，移除误加的宽泛 tests/ 忽略规则。代码审查后提交 fde2564（feat(gateway): add command persistence seam）。

**2026-10-19T08:53:34Z**

关联 Gitee Pull Request #9：https://gitee.com/qi-yueran/ai4science/pulls/9（目标 develop）。实现提交：fde2564；目录与 uv 迁移提交：e5c64b2。
