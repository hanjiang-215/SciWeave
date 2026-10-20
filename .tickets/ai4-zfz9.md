---
id: ai4-zfz9
status: closed
deps: []
links: []
created: 2026-10-20T06:49:41Z
type: task
priority: 1
assignee: Frank Qi
parent: ai4-yyy9
tags: [wayfinder:grilling]
---
# Gateway MCP 对外协议版本、鉴权与错误契约

## Question

在已确定的 MCP（Streamable HTTP）Owner 通道和六个工具基础上，收敛最小 Gateway 对外协议的版本声明、调用者身份校验、本地开发令牌验证、授权失败、输入校验、领域状态冲突与内部故障的工具级错误契约；明确 HTTP 传输失败与 MCP 工具错误的边界。此票不实现多人 Owner 授权绑定、跨网络部署或具体 SDK 选型。

## Design

## Scope

本票只裁决 Owner MCP 客户端可观测的协议行为，以便后续规格与测试可实施。

## Acceptance Criteria

## Acceptance Criteria

- [ ] 明确协议/能力版本的最小表达与兼容策略。
- [ ] 明确本地开发令牌的身份校验边界及未认证调用的表现。
- [ ] 明确成功、输入校验、未找到、状态冲突、幂等键冲突、不可取消与内部故障的结构化工具错误。
- [ ] 区分 MCP 传输/协议失败和业务工具错误。
- [ ] 不引入多人 TaskNode Owner 授权、跨网络部署或未选定 SDK 依赖。


## Notes

**2026-10-20T07:24:10Z**

Resolution（2026-10-20）：Gateway 最小 MCP 对外协议采用以下契约。\n\n1. 版本：MCP 初始化完成协议版本协商；认证后的 MCP health 返回 gateway_api_version="v1"。v1 仅兼容性新增可选字段或工具；删除、收紧既有字段或改变语义时升级主版本。\n2. 鉴权和调用者：每个 MCP 请求均通过 Authorization: Bearer <token> 使用环境变量提供的本地开发令牌校验。启动配置同时提供 caller_id；校验成功后，Gateway 将该 Caller 写入 OwnerCommand 和 AuditEvent。首版仅做此轻量校验，不实现 OAuth、多调用者、scope 或 TaskNode Owner 授权。缺失或无效令牌返回 HTTP 401，不创建 OwnerCommand、ExecutionRecord 或 AuditEvent。\n3. 结果和错误：成功结果仅在 MCP content 返回一个 JSON 文本对象；首版不声明 outputSchema 或返回 structuredContent。无效 JSON-RPC、未知工具、缺失必填参数及类型不符由 MCP/JSON-RPC 协议错误表达。参数已验证并进入工具后的业务失败以 isError=true 返回 JSON 文本 {error:{code,message}}；稳定错误码为 not_found、invalid_state、unavailable、internal。错误不得含异常、堆栈、令牌、文件路径或原始命令。\n4. 健康：无令牌的回环 HTTP 探针仅返回 status 和 gateway_api_version；监听地址、端口由环境变量配置。认证后的 MCP health 返回完整分项健康。\n5. 幂等：submit_owner_command 与 review_execution 的 idempotency_key 分别在各自工具内全局唯一；同一键返回首个持久化结果并标记 duplicate=true，不比较后续参数。调用方必须为每个逻辑操作生成新键。\n6. 取消和列表：cancel_execution 对存在的执行总返回 {execution_id, execution_status, accepted}；accepted 仅表示本次取消请求已被 Gateway 接受，已终结、人工接管或已取消则为 false，不是工具错误。不存在的执行返回 not_found。list_pending 可选按 task_node_id 过滤，一次返回全部待处理记录，按 created_at、execution_id 升序；首版不分页。\n7. 状态归属：OwnerCommand 是不可变的命令接收和审计留痕，不维护生命周期状态机；唯一的 Gateway 工作流状态机属于 ExecutionRecord。accepted 专指 ExecutionRecord 的结果已被 TaskNode Owner 接纳，不等于命令接收，也不等于领域 Buffer 接收。Buffer 及其状态机不在本阶段设计；执行接纳不自动创建 Buffer。\n\n依据：MCP 工具规范区分 JSON-RPC 协议错误和 isError 工具执行错误；HTTP MCP 鉴权使用 Authorization Bearer 令牌。首版刻意省略分页、结构化输出、OAuth 和多人授权，以优先完成可测试闭环。
