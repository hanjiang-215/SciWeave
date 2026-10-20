---
id: ai4-2sdn
status: closed
deps: [ai4-9hcj]
links: []
created: 2026-10-17T02:59:22Z
type: research
priority: 1
assignee: hanjiang
parent: ai4-ru15  # 动态科研协作平台需求地图
tags: [wayfinder:research, wiki, terminusdb, proposal, ai4science]
---
# TerminusDB candidate branch 状态标记与只读归档能力验证

## Question
验证 TerminusDB 12.0.8 是否原生支持为 branch 保存治理状态，例如 selected、not_selected、rejected、abandoned；是否支持将 branch 设为只读、归档或安全删除。若 TerminusDB 不支持，确定 Wiki 平台应把哪些状态和权限放在平台结构化记录中，并设计可复现的验证步骤。只研究 Wiki candidate branch，不修改正式分支，不涉及 Research Mapping 产品规则。

## Acceptance Criteria
记录 TerminusDB branch 元数据、备注、权限、删除和写入控制的实际能力；验证分支状态能否独立于 Commit 保存；验证只读、归档、删除或替代方案；给出 Wiki 平台状态模型和审计建议；实验使用临时数据库并清理实验数据。

## Answer
验证时间：2026-10-17；TerminusDB 12.0.8；TerminusDB Store 0.19.8；服务地址 `http://127.0.0.1:6363`。实验数据库均为临时数据库，实验结束后已删除。

### 验证结果

1. **Branch 没有可用的原生治理状态字段**
   - 使用 `POST /api/branch/admin/<db>/local/branch/candidate` 创建分支时，实际需要的核心参数是 `origin`，例如 `{"origin":"admin/<db>/local/branch/main"}`。
   - 在创建请求中附带 `label`、`comment`、`status` 等字段，接口仍只返回普通 `BranchResponse`，没有返回或暴露这些字段的持久化状态。
   - 对 branch 资源执行 `GET` 返回 `405 Method Not Allowed`；对 `PATCH` 和 `PUT` 返回 `405 Method Not Allowed`。没有在公开 HTTP API 中找到读取或更新 branch 治理元数据的接口。
   - 因此 `selected`、`not_selected`、`rejected`、`abandoned` 等状态不能依赖 TerminusDB branch 原生属性保存。

2. **没有验证到原生只读或归档状态**
   - Branch API 没有发现把分支设为只读、锁定或归档的操作。
   - 通过禁止平台写入来实现只读是平台权限和状态控制，不是 TerminusDB branch 的原生状态。

3. **Branch 支持删除，包括含有候选 Commit 的分支**
   - 使用 `DELETE /api/branch/admin/<db>/local/branch/candidate` 成功删除 candidate branch，HTTP 状态为 `200`。
   - 实验还在 candidate branch 中成功写入一个新的 WikiDocument，产生候选 Commit 后再次删除该分支，仍然返回 `200`。
   - 删除后继续读取该 branch 返回 `UnresolvableAbsoluteDescriptor`，说明该分支不再作为可查询目标存在。
   - 删除是破坏性操作，不能承担 Wiki 的审计归档语义；平台应在任何删除前保存 branch、head、Proposal、Commit 和审核事件，第一阶段默认不删除。

4. **Branch 创建请求不能承担 Proposal 状态**
   - TerminusDB branch 只表达存储分支和提交历史，不知道 Proposal 是否被选择、拒绝或废弃。
   - `TerminusDB Commit` 也只表达存储变化，不能表达 Project Owner 的选择结果或正式化结果。

### Wiki 平台规则建议

- `Proposal` 保存 `selected`、`not_selected`、`rejected`、`abandoned`、`merged` 等治理状态；不要把这些状态塞入 TerminusDB branch。
- Proposal 保存 candidate branch、candidate head、base Formal WikiRevision、所有 Commit、Merge Request Buffer、dry-run 结果、Project Owner 选择和通知记录。
- 未选中的 candidate branch 默认保留并禁止继续写入；平台以 Proposal 状态和权限控制实现“只读归档”。
- 不需要物理删除 branch。只有在平台完成审计快照、确认保留期和删除授权后，才可以把 TerminusDB 删除作为存储清理动作；删除不能改变平台审计链。
- 被选中的方案以新的 Formal WikiRevision 进入 formal branch；未选中的 Proposal 记录为 `not_selected`，提交者可以基于新的 Formal WikiRevision 创建后续变更。
- 分支状态、只读控制、归档期限、删除授权和通知记录属于 Wiki 平台结构化治理事实，不属于 TerminusDB branch 原生事实。

### 可复现实验摘要

```text
GET    /api/branch/.../candidate       -> 405 Method Not Allowed
PATCH  /api/branch/.../candidate       -> 405 Method Not Allowed
PUT    /api/branch/.../candidate       -> 405 Method Not Allowed
POST   /api/branch/.../candidate       -> 创建分支，支持 origin
DELETE /api/branch/.../candidate       -> 200，含候选 Commit 的分支也可删除
```

结论：TerminusDB 提供 branch 创建、写入和删除能力，但不提供本项目需要的 Proposal 状态、只读归档或正式治理标记。Wiki 必须把分支治理状态和审计信息保存在平台结构化记录中；candidate branch 物理删除只能作为受控存储清理，不能作为业务上的“废弃”或审计记录。

## Review conclusion (2026-10-18)

验证结果已被 `ai4-5j2j` 的固定版本和服务说明引用。该票据支持的产品结论是：TerminusDB 存储能力不能替代 Proposal 状态、Project Owner 审核或 AuditEvent；普通研究人员不应直接操作 branch。由于 `ai4-9hcj` 是 Mapping 存储验证前置，已补充依赖关系；Wiki 相关能力仍不阻塞首版 Mapping 演示。
