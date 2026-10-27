---
id: ai4-x0ay
status: open
deps: [ai4-cxnm, ai4-tj83, ai4-4r0h]
links: []
created: 2026-10-27T10:19:35Z
type: feature
priority: 1
assignee: Frank Qi
tags: [toolkit, task-agent, workflow, fast-agent, preset]
---
# 预设文献 Agent 与多 Agent 工作流

套件要出厂就能跑起来一个真实可用的 agent，而不是让研究员从空目录开始写。本票交付 1+1 预设：一个多 agent 的文献工作流，和一个单 agent 的最小样例。

前置约束全部来自 2026-10-27 的设计轮次（grill-with-docs，四轮），下面每条都注明了它在真实代码里的依据。

## 一、fast-agent 的编排器不能挂 MCP，这决定 agent 的切分

`fast_agent/core/direct_decorators.py` 里，`orchestrator` 与 `parallel` 的 `servers` 被**硬编码为空**：

```python
# orchestrator
return _decorator_impl(self, AgentType.ORCHESTRATOR, ...,
    servers=[],   # Orchestrators don't connect to servers directly
# parallel
return _decorator_impl(self, AgentType.PARALLEL, ...,
    servers=[],   # Parallel agents don't connect to servers directly
# router —— 可挂
    servers=servers,
# agent（Agents as Tools）—— 可挂，且能带子 agent
    AgentType.BASIC, servers=servers, child_agents=agents,
```

而 `orchestrator(name, *, agents: list[str], ...)` 的 `agents` 只是**按名字引用**已注册的 agent。所以编排器本身拿不到 `create_draft` 与 `send_notification`，必须把这些能力放在子 agent 上。

## 二、Agent 切分

| agent | fast-agent 类型 | 挂载的 MCP 卡 | 职责 |
| --- | --- | --- | --- |
| `literature-searcher` | `agent` | `literature-search` | 联网检索、取摘要 |
| `mapping-reader` | `agent` | `research-mapping`（只读卡） | 查 TaskNode、取 `task_owner_id` |
| `wiki-reader` | `agent` | `research-wiki`（只读卡） | 查已有正式词条，避免重复建条目 |
| `draft-writer` | `agent` | `draft-buffer` + `email-service` | 写草稿、发通知 |
| `literature-agent` | `orchestrator` | **无** | 解读意图、规划步骤、派活给前三个 reader |

工作流声明（放 `libs/workflow-libs/literature-agent.yaml`）：

```yaml
version: 1.0.0
workflows:
  literature-agent:
    type: Orchestrator
    plan_type: iterative
    plan_iterations: 2
    entry_agent: literature-agent
    sub_agents: [literature-searcher, mapping-reader, wiki-reader]
    final_writer: draft-writer
```

**`final_writer` 由 runtime 在编排结束后确定性调用，不交给编排器的 plan 决定。** 理由：`plan_type="full"` 的 plan 由 LLM 生成，它不保证 `draft-writer` 排在最后，也不保证一定被调用；而草稿写入与发通知是必须发生且只能发生一次的动作。这条也是 `ai4-sxpw` 里 `final_writer` 字段第一次获得真实含义：它是「草稿署名 agent」，同时被真实调用一次。

## 三、草稿由 agent 写，runtime 只装配

研究员侧有两种「agent」：研究员本人的 Personal Agent（Codex 之类）与 Work Agent 运行时。本票采用的分工是：**写草稿的动作由 agent 通过 MCP 完成，runtime 只负责配置好草稿箱 MCP 并保证幂等**。

由此带来一个必须解决的问题：`draft_id` 怎么回到 runtime。现在（`runtime.py` / `workflows.py`）是 runtime 直接调 `self.drafts.write()` 拿返回值，agent 自己写之后这条路断了，`store.complete(execution, draft_id)` 就没有入参。

采用的办法：**runtime 由 `execution_id` 派生 `idempotency_key`，注入 agent 输入；跑完后用这个 key 调 `list_drafts` 反查 `draft_id`。** 不用「取最新一条」（并发下会认错），也不让模型在输出里返回 UUID（一旦记错或改写就永久错位）。

反查不到时记 `failed` + 稳定错误码 `draft_id_missing`，不伪造完成。

## 四、确认身份的卡：`create_draft` 的必填项

`libs/mcp-libs/draft-buffer/mcp.json` 的 `create_draft` 必填 `namespace` / `kind` / `title` / `payload` / `submitted_by` / `idempotency_key`。`buffer/src/draft_buffer/service.py:33` 的 `_mutate("create_draft", idempotency_key, ...)` 按这个 key 做幂等。所以上面第三节的做法与服务的既有语义一致，不需要改服务。

## 五、通知：agent 发，`dedupe_key` 由 runtime 注入

`send_notification` 必填 `notification_id` / `dedupe_key` / `notification_kind` / `recipients` / `subject` / `body` / `related` / `schema_version`。收件人是 `{"principal_id": ...}` 形状，由 email-service 的 `RegistryRecipientResolver` 调 Registry 的 `get_principal_contact` 解析成邮箱。

分工：**查 owner 属于 agent（领域知识），`dedupe_key` 属于 runtime（幂等控制）。**

- `mapping-reader` 用 `get_formal_mapping` 取当前正式图，找 TaskNode 文档的 `task_owner_id`（该字段在 `candidate_submission.py` 的 TaskNode 必填清单里，`dashboard_source.py:72` 也在读）；
- 收件人 = `[{"principal_id": task_owner_id}]`，`notification_kind` 用 `task_agent_run_finished`；
- `dedupe_key` 与第三节的 `idempotency_key` 同源（都由 `execution_id` 派生）。

**已知风险：** `ai4-dp9t`（open，hanjiang）正在修「Registry 的三个永久错误码全被压成 `registry_unavailable`」。在它修好之前，通知失败看不出真实原因，本票侧只能如实记 `notification_failed`，**不做重试风暴**。

## 六、`allowed_mcp_resources` 要能真的变成 fast-agent 的 MCP 配置

`config.py:169` 已经能把 agent 的 `allowed_mcp_resources` 转成 `{"servers": [...]}`，但 `fast_agent_runtime.py:168` 生成的 `fast-agent.yaml` 只有两行：

```yaml
compaction:
  auto: false
session_history: true
```

**一个 MCP server 都没配**，所以 agent 手里没有任何 MCP 工具。需要把 `libs/mcp-libs/*/mcp.json` 的 `transport` / `endpoint.url_env` / `environment` 翻译成 fast-agent 的 `mcp.servers.<name>` 段，且**只注入该 agent 声明的那几张卡**。

## 七、单 agent 最小样例

除文献工作流外，再给一个单 agent 预设（`libs/agent-libs/` 之外的独立 agent 定义），用于「我就想要一个能收活、能写草稿的 Task Agent」这种最朴素的用法，也作为研究员改写的起点。

## Acceptance Criteria

- [ ] `libs/workflow-libs/literature-agent.yaml` 含四个子 agent 与一个编排器，全部通过 `load_workflow_yaml` 校验（含 `version: 1.0.0`）。
- [ ] 四个子 agent 各自的 `allowed_mcp_resources` 与第二节的表逐条一致；编排器为空。
- [ ] 生成 `fast-agent.yaml` 时按 `allowed_mcp_resources` 注入 `mcp.servers`，未声明的卡不注入；补测试覆盖「只注入声明的」。
- [ ] `final_writer` 由 runtime 在编排结束后调用一次，不由 plan 决定；补测试：编排器 plan 里不含 `draft-writer` 时它仍被调用。
- [ ] `draft_id` 用 `execution_id` 派生的 `idempotency_key` 反查获得；反查失败记 `failed` + `draft_id_missing`，不写伪造的 `draft_id`。
- [ ] 通知的 `dedupe_key` 由 runtime 注入（与 `idempotency_key` 同源）；收件人取 `task_owner_id`；email-service 不可用时只记 `notification_failed`，不重试。
- [ ] 单 agent 最小样例可加载、可跑通 passthrough 路径。
- [ ] 端到端测试在**无真实 API key** 的前提下跑通：使用 passthrough runtime + 假 MCP，验证「入队 → 编排 → 写草稿 → 通知」的状态流转与 `draft_id` 落库。
- [ ] 文档说明每个 agent 的职责、挂哪些卡、为什么这么切；注明 `Orchestrator` 与 `Parallel` 不能挂 MCP 这一 fast-agent 约束及其来源。
- [ ] runtime 全量测试通过；`compileall` 与 `git diff --check` 通过。

## Blocked by

- [ai4-cxnm](ai4-cxnm.md)：`literature-searcher` 依赖的 `literature-search` 卡与服务。
- [ai4-tj83](ai4-tj83.md)：只读卡的工具面必须先收敛，否则注入给 agent 的是带写正式域能力的全集。
- [ai4-4r0h](ai4-4r0h.md)：`WORKFLOW_LIBS_PATH` 未实现，工作流加载不出来。

## Not in Scope

- 不实现 `literature-search` 服务本身（`ai4-cxnm`）。
- 不改卡片工具面（`ai4-tj83`）。
- 不做中央 Agent、不做预览规则链。
- 不引入真实 API key；自动化基线保持 passthrough，真实 key 由研究员自填。
- 不改 ExecutionRecord、Worker Lease 的服务模板接口（`ai4-z3z4` 的边界仍然有效）。

## Notes

**2026-10-27 立项（Frank Qi）**

> *This was generated by AI during triage.*

身份核对：assignee `Frank Qi`、分支 `feature/frank-qi`、`git config user.name=Frank Qi`，三者一致。

本票是 2026-10-27 四轮设计（grill-with-docs）的落地票。四轮结论按序：预设取「默认配置，研究员从能跑的东西上改」；工作流沿用 `ai4-sxpw` 的 YAML 协议；文献 agent 必做四件事（解读意图、分配子 agent、写 buffer、发邮件）；预设 search 能力并自建 MCP；resources 放 `libs/agent-libs` 与 `libs/workflow-libs`。

关键结构决策来自实测而非推测：`fast.orchestrator` / `fast.parallel` 的 `servers=[]` 是逐行读 `direct_decorators.py` 确认的；`fast.agent(agents=[...])` 走 `AgentType.BASIC` + `child_agents` 也是同一处确认的。第 18 条原文「Orchestrator 可以先在 agent-libs 中定义这些 agent，再接入 orch」——经核对成立，`agents: list[str]` 就是按名字引用已注册的 agent。

与 `ai4-za77` / `ai4-cdia` 不重复：那两张交付的是套件的骨架与技能组，本票交付的是「骨架里装什么内容」。
