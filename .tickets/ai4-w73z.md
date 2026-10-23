---
id: ai4-w73z
status: open
deps: []
links: [ai4-9322, ai4-6ljq, ai4-orpg, ai4-ujvn]
created: 2026-10-23T02:53:55Z
type: feature
priority: 1
assignee: hanjiang
tags: [mcp, mapping, wiki, audit, centre-control, implementation, ready-for-agent]
---
# Research Mapping 与 LLM-Wiki 对外管理接口及权限分层

为 Research Mapping 与 LLM-Wiki 实现可供研究员端侧 Agent、中央 Agent 和 Project Owner 调用的对外管理接口，优先采用两套独立的领域管理 MCP；不得把两个领域合并为一个跨域接口，也不得让调用方绕过领域服务直连 SQLite 或 TerminusDB。现有领域应用服务已具备正式查询、候选提交、候选审阅和正式化能力，本票负责把这些内部能力包装成稳定的对外工具、完成调用方权限隔离、启动配置和验证。\n\n请重点关注 Gitee Pull Request #27（https://gitee.com/qi-yueran/ai4science/pulls/27）及其相关接口约定；共享部分的接口层调用留痕已经实现，代码位于 sci-weave/centre-control/shared/audit-trail。对外接口必须在服务启动时打开并初始化审计库，并按共享包约定记录工具调用；不要在领域服务内部重复接入或自行定义另一套审计事件。

## Design

## 对外接口边界\n\n- 分别为 Research Mapping 和 LLM-Wiki 提供独立的管理 MCP；工具通过应用服务调用，不直连领域存储。\n- 至少覆盖正式内容只读查询、候选查询/读取、候选提交、候选审阅所需入口、Owner 正式化/恢复入口，以及健康检查或启动失败状态。\n- 工具输入输出使用稳定、可序列化的 DTO/JSON；返回稳定错误码，区分参数拒绝、无权访问、基准过期、存储明确失败和结果未知。\n- 通过环境变量配置监听地址、端口、领域存储地址、凭据和 SCIWEAVE_AUDIT_SQLITE_PATH；源码、测试和文档不得写死部署路径、端口或凭据。\n\n## 权限分层\n\n服务端按调用方能力面执行权限，不以客户端自报角色或登记记录替代鉴权。至少明确并测试以下档位：\n\n1. **只读**：读取当前正式 Mapping/Wiki、候选摘要或候选固定头时，只能读取调用方被授权范围；中央 Agent 可按既定开放面读取全部候选和正式版本，端侧 Agent 不自动获得全部数据。\n2. **只写候选**：研究员/端侧 Agent 只能提交自己的草稿或候选变更，并受领域校验、精确正式基准、幂等键和候选隔离约束；不得直接修改正式版本、代替 Owner 审核或推进正式化。\n3. **候选审阅**：明确谁可以创建/读取审阅材料、记录预审结论和提交候选审核决定；预审结论不得等同于 Project Owner 的正式发布批准。\n4. **候选转正式**：只有 Project Owner 或已验证的 Owner 权限可以执行正式化/恢复；必须保留候选头、正式基准、批准决定和 operation identity 校验，不能通过普通写候选工具绕过正式化门禁。\n5. **中央 Agent**：按既有开放面允许读取两套领域的候选与正式版本、追加预审日志、必要时创建混合候选；不得写正式版本、修改已有候选、写草稿接纳状态或代替 Owner 正式发布。\n\n需要把每个工具归入能力档位，并对未授权调用返回稳定 denied 错误；不能仅依赖提示词隐藏工具。两个领域的对象、存储、候选和正式化权限保持隔离。\n\n## 共享留痕接入\n\n- 使用 `sciweave-audit-trail` 的 `open_connection`、`init_audit_table`、`record_attempted`、`call_scope`/`begin_call`/`finish_call`。\n- 服务启动时打开审计 SQLite 并初始化表；初始化失败不得启动对外服务。\n- 读工具结束后记录 `attempted`，留痕失败按共享包约定 fail-open；写工具执行前记录 `invoked`，留痕失败时阻止业务执行，成功或失败后记录 `completed`。\n- 记录 `caller_id`、`channel_id`、`caller_type`、服务名、工具名、目标对象标识、参数摘要、结果和错误码；不得写入正文、凭据或完整入参。\n- 留痕发生在 MCP/HTTP 对外接口层，领域应用服务内部不重复调用共享包。\n\n## 依赖与范围\n\n- 复用现有 Research Mapping 与 LLM-Wiki 应用服务，不重写领域治理逻辑。\n- 复用 `ai4-gvan` 已实现的共享留痕包；如需调整共享包接口，先说明原因并更新对应实现票，不复制实现。\n- 与 `ai4-ujvn` 的调用方开放面和 `ai4-t2wc` 的中央 Agent 开放面保持一致；若发现冲突，先在本票 Notes 记录并提出修订，不自行覆盖既有决策。\n- 本票不实现 Web 看板前端、不实现端侧 Agent runtime、不把领域 MCP 改造成 Gateway MCP。

## Acceptance Criteria

- [ ] Research Mapping 和 LLM-Wiki 分别提供独立、可启动、可配置的对外管理接口；调用通过应用服务完成，不直连领域存储。\n- [ ] 工具目录和输入输出契约覆盖正式只读、候选读取/提交、候选审阅、Owner 正式化/恢复及健康检查；每个工具标明权限档位。\n- [ ] 只读、只写候选、候选审阅、候选转正式、中央 Agent 五类能力边界均有服务端鉴权与测试；未授权调用返回稳定 denied 错误。\n- [ ] 端侧 Agent、研究员、中央 Agent、Project Owner 的开放面与 `ai4-ujvn`、`ai4-t2wc` 一致；不能通过隐藏工具名、直接存储访问或普通候选写入绕过正式化权限。\n- [ ] 候选提交保留精确正式基准、候选隔离和幂等语义；正式化保留 Owner 授权、candidate head、operation identity 和失败/恢复语义。\n- [ ] 对外服务启动时使用环境变量配置地址、端口、存储和审计库；审计库打开或建表失败时服务不启动。\n- [ ] 所有对外工具按 `sci-weave/centre-control/shared/audit-trail` 的接口层调用账本留痕：读调用 `attempted` fail-open，写调用 `invoked`/`completed` fail-closed；审计记录不含正文、凭据或完整入参。\n- [ ] 审计接入位于对外接口层，领域应用服务内部无重复留痕；至少验证成功、拒绝、业务失败、审计库不可用和进程中断留下未完成调用等路径。\n- [ ] 关注并复核 Gitee Pull Request #27 的接口/聚合 API 变化，必要时在实现中保持兼容或记录冲突。\n- [ ] 按各子项目锁文件完成最小安装、测试和编译验证，并将命令、结果和关联 PR 回写本票 Notes；不引入未登记依赖。

