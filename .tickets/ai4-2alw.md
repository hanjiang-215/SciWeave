---
id: ai4-2alw
status: closed
deps: [ai4-9hcj]
links: []
created: 2026-10-16T04:16:17Z
type: task
priority: 1
assignee: qiyueran
parent: ai4-ru15
tags: [wayfinder:task, terminusdb, mapping, ai4science]
---
# TerminusDB 候选分支与草稿工作区行为验证

## Question
在 TerminusDB 12.0.8 中确认 HTTP API 和原生命令创建候选分支的正确参数与行为：候选分支是否能从 main 创建、是否可以在分支中提交节点变更、如何查看分支差异、如何合并到 main，以及是否存在不产生正式 Commit 的草稿工作区。验证结果用于决定 Proposal 待审核变更应放在 TerminusDB 分支、独立数据库还是平台侧状态中。

## Acceptance Criteria

记录可复现的分支创建、提交、Diff、合并/恢复命令或明确证明不支持；给出待审核 Proposal 的存储建议；不得使用未确认的 Git 式分支语义。

## Notes

**2026-10-16T12:50:59Z**

本轮开始验证。验证范围已结合单一 Mapping 决策收窄为：确认 TerminusDB 12.0.8 是否支持隔离的候选分支或工作区；候选对象是否能与 main 正式查询隔离；是否能通过 Commit/History/Diff 追踪草稿变化；批准后是否能形成明确的正式 Commit；若原生能力不足，确定平台侧 Proposal 状态或独立候选数据库作为替代。第一阶段只要求历史追溯，不要求数据库级回滚。

**2026-10-16T13:37:04Z**

## Validation results

验证时间：2026-10-16；服务版本：TerminusDB 12.0.8，TerminusDB Store 0.19.8；服务地址：http://127.0.0.1:6363。使用临时数据库 `ai4sci_branch_test_20261016`，验证结束后已删除。

### 可复现操作与结果

1. 创建临时数据库：
   `curl -u admin:root -X POST http://127.0.0.1:6363/api/db/admin/ai4sci_branch_test_20261016 -H 'Content-Type: application/json' -d '{"label":"AI4Sci branch validation","comment":"temporary test database","schema":true}'`
2. 通过 `POST /api/document/admin/<db>?graph_type=schema` 创建 `TaskNode` 和 `DependencyEdge` Schema；通过 `POST /api/document/admin/<db>/local/branch/main` 写入 A、B 和 A→B，得到正式基线 Commit `5a0zds6rjwlge6ib0u87y18dnopwylb`。
3. 通过：
   `POST /api/branch/admin/<db>/local/branch/candidate`
   请求体：`{"origin":"admin/<db>/local/branch/main"}`
   成功创建 candidate 分支。候选分支创建后能读取 main 的 A、B 和 A→B。
4. 使用正确的分支路径：
   `/api/document/admin/<db>/local/branch/candidate`
   写入 TaskNode C、DependencyEdge C→B，并更新 TaskNode A。candidate 可读取这些数据，main 仍只包含基线 A、B 和 A→B；main 的 head 保持不变。候选分支连续写入产生 Commit：`7neobhdw95kz76xhkflsdlw1a0da12j`、`0ei3ntmw6a6ewx1f1lb9go3jkengp5w`、`v1a2n5al1bq6lnwtucnckr7u0kq2l2u`。
5. 通过：
   `POST /api/diff/admin/<db>/local/branch/candidate`
   请求体：`{"before_data_version":"main","after_data_version":"candidate"}`
   成功返回完整结构 Diff，包括新增 C、新增 C→B，以及 A 的 name/status 字段变化。
6. 通过：
   `GET /api/history/admin/<db>/local/branch/candidate?id=TaskNode%2FA`
   成功返回 A 的 candidate update Commit 和基线 Commit，包含 author、identifier、message、timestamp。
7. 发送 `commit=false` 写入 TaskNode D，HTTP 返回成功；D 出现在 candidate 数据中，并在 candidate log 中生成 `ValidCommit/q21waaysejikc53mo8df11364ux0k0b`。因此 `commit=false` 不是无提交工作区。
8. 通过：
   `POST /api/rebase/admin/<db>/local/branch/main`
   请求体：`{"rebase_from":"admin/<db>/local/branch/candidate","author":"admin","message":"approve proposal into formal main"}`
   成功返回 `api:common_commit_id` 和 `api:forwarded_commits`，之后 main 可读取 candidate 的 C、C→B、A 修改和 D。TerminusDB 的 rebase 可以承担候选分支变更推进，但它会按存储状态推进，不能判断 Proposal 是否已获负责人批准，也不会自动把 draft 状态变成 formal。
9. 创建 candidate2 后，让 main 和 candidate2 同时修改 TaskNode A，再执行 rebase；操作返回 `RebaseSchemaValidationError`，main 保留自己的修改，没有部分写入。冲突错误包含冲突 Commit 和 Schema witness，但平台仍需将该结果映射为 Proposal `conflict` 或 `stale`。

### 重要纠正

客户端源码显示分支必须进入 URL 路径，例如 `/local/branch/candidate`；此前使用 `?branch=candidate` 的请求会被服务忽略，不能作为分支隔离测试证据。有效测试已全部使用路径形式重跑。

### 结论

- TerminusDB 12.0.8 原生支持候选分支：可以从 main 创建、独立写入、生成 Commit、查询 History、生成跨分支 Diff，并通过 rebase 将候选提交推进到 main。
- TerminusDB 不提供满足本项目要求的无 Commit 草稿工作区；任何文档写入，包括 `commit=false`，都会形成 ValidCommit。
- rebase 是存储层分支整合操作，不等于负责人审核；它可能把节点的 `draft` 状态和其他候选数据一起推进到 main。因此平台必须在正式查询层过滤状态，并由平台先验证 Proposal 审批、base_commit 未过期、冲突检查和变更范围，再执行受控正式化。
- 不建议使用数据库 reset 表示回滚；已有验证证明 reset 会移动分支指针。第一阶段应保留所有 Commit，通过 Proposal 审批后再进行正式化，历史追溯由 Commit/History/Diff 完成。
- 推荐方案：每个 Proposal 使用一个从当前正式 Commit 创建的 TerminusDB candidate branch；平台保存 proposal_id、base_commit、candidate_head、审核状态、审核人、审核时间、评语和 resulting FormalRevision。普通查询固定读取平台认定的正式 Commit，并过滤非 formal 节点/边；不得直接读取 main 当前 head 作为正式事实，除非平台已完成正式化。
- 若候选分支产生大量中间 Commit，平台可以在负责人批准后使用 rebase/squash 形成正式存储版本，但必须保留 candidate_head 与正式 Commit 的关联；具体是否 squash 留待正式规格阶段决定。
