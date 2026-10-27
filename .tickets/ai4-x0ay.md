---
id: ai4-x0ay
status: open
deps: [ai4-cxnm, ai4-tj83, ai4-4r0h, ai4-4zjz]
links: [ai4-4zjz]
created: 2026-10-27T10:19:35Z
type: feature
priority: 1
assignee: Frank Qi
tags: [toolkit, task-agent, workflow, fast-agent, preset]
---
# 预设文献 Agent 与多 Agent 工作流

套件要出厂就能跑起来一个真实可用的 agent，而不是让研究员从空目录开始写。本票交付 1+1 预设：一个多 agent 的文献工作流，和一个单 agent 的最小样例。

前置约束全部来自 2026-10-27 的设计轮次（grill-with-docs，四轮）与同日复审核对，下面每条都注明了它在真实代码里的依据。

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
| `draft-writer` | `agent` | `draft-buffer` + `email-service` | 写草稿、发通知、回传 `draft_id` |
| `literature-agent` | `orchestrator` | **无** | 解读意图、规划步骤、派活给前三个 reader，并汇总子 agent 产出 |

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
    summarizer: literature-agent
    final_writer: draft-writer
```

`summarizer: literature-agent` 与 `libs/workflow-libs/orchestrator-example.yaml` 的写法一致：Orchestrator 类会先调 `summarizer` 汇总子 agent 产出，再调 `final_writer` 落草稿。

**`plan_type` / `plan_iterations` 现在会被静默丢弃。** `WorkflowDefinition` 的字段只有 `['name','workflow_type','entry_agent','sub_agents','summarizer','final_writer']`，实测 `hasattr(w, 'plan_type')` 为 `False`，`workflow_to_fast_agent_input()` 也不输出它们。所以本节 YAML 要想真的生效，必须先给 `WorkflowDefinition` 补这两个字段并让转换层透出——这是本票要做的事，属于协议层扩展。「YAML 里写了不生效的键要报错」那一半归 `ai4-4r0h`（本票的 dep）：它管的是配置加载层的静默容忍。

**`final_writer` 的现状与要修的点。** `workflows.py:57-58` 现在**已经**是 runtime 在编排结束后确定性调用 `final_writer`：

```python
final = self._call(workflow.final_writer, self._render(intermediate))
draft_id = self.drafts.write(target_id=target_id, payload=final)
```

所以「不交给 plan 决定」不是本票要新增的行为。真正的问题是**四类工作流都无条件调一次 `final_writer`**，包括 `Router` 与 `Agents as Tools`——这两类的 `entry_agent` 产出已经是答案，再调一次就是纯多余的模型调用。本票的决定：**保留这次调用**，把它明确成「按草稿署名格式重写一遍」的 LLM 步骤（写入草稿的 payload 必须与 agent 的思考产物分离），并在文档里说清它是真实模型调用而非字符串转换。不要按类型做分支——那会让四类的状态机与调用计数各不相同，测试成本远大于省下的一次调用。

## 三、草稿由 agent 写，`draft_id` 由 agent 结构化回传

研究员侧有两种「agent」：研究员本人的 Personal Agent（Codex 之类）与 Work Agent 运行时。本票采用的分工是：**写草稿的动作由 agent 通过 MCP 完成，runtime 只负责配置好草稿箱 MCP 并保证幂等**。

由此带来一个必须解决的问题：`draft_id` 怎么回到 runtime。现在（`workflows.py:59`）是 runtime 直接调 `self.drafts.write()` 拿返回值，agent 自己写之后这条路断了，`store.complete(execution, draft_id)` 就没有入参。

**采用的办法：agent 在最终输出里以固定 JSON 形状回传 `draft_id`。**

`draft-writer` 的 instruction 强制规定：调用 `create_draft` 后，最终回答必须是且仅是一个 JSON 对象

```json
{"draft_id": "<create_draft 响应里的 draft_id>", "summary": "<一句话结论>"}
```

`create_draft` 的响应里本来就有 `draft_id`，实测返回 `{'draft_id': '3f12df3e-...', 'status': 'drafting', 'snapshot_commit': 'c'}`，所以这是让 agent 转述它刚拿到的东西，不需要额外查询。

runtime 侧：

- 用 `json.loads` 解析 `final_writer` 的输出，取 `draft_id`；
- 校验形态为 UUID（`uuid.UUID(value)` 且 `str(parsed) == value.lower()`）；
- 落库时把 `draft_id` 来源标记为 `agent_reported`，`query_execution` 一并返回该标记；
- 解析失败或形态不合法 → `failed` + 稳定错误码 `draft_id_missing`，**不写伪造的 `draft_id`**；
- `idempotency_key` 仍由 `execution_id` 派生并注入 agent 输入，保证重放不产生第二份草稿。

**为什么不用「runtime 用 `idempotency_key` 反查 `list_drafts`」。** 这条曾经是候选方案，2026-10-27 复核时被实测推翻：草稿箱的 `_authorize_namespace` 要求调用者在该命名空间的 `reviewers` 里，而套件 token 映射出的 actor 就是 `submitted_by`（提交者），实测提交者自己调 `list_drafts` / `read_draft` 都返回 `forbidden`。且 `list_drafts` 的入参只有 `namespace` / `status` / `submitted_by`，根本没有按 `idempotency_key` 或 `source_execution_record_id` 过滤的能力。反查方案在当前草稿箱协议下不存在实现路径。

**为什么不让套件 token 绑一个 reviewer actor。** 那样 agent 能读该命名空间**全部**草稿，是把研究员侧凭据的权限放大到审核人，与 `ai4-tj83` 正在收敛的能力面方向相反。

**必须承认的代价**：runtime 无法独立验证草稿真的写成了，它信任的是 agent 的自述。这正是要加 `agent_reported` 标记的原因——不要把「agent 说写成了」伪装成「runtime 验过」。

## 四、确认身份的卡：`create_draft` 的必填项

`libs/mcp-libs/draft-buffer/mcp.json` 的 `create_draft` 必填 `namespace` / `kind` / `title` / `payload` / `submitted_by` / `idempotency_key`。`buffer/src/draft_buffer/service.py:33` 的 `_mutate("create_draft", idempotency_key, ...)` 按这个 key 做幂等。

`kind` 是**封闭枚举**（`service.py:12-13`）：

```python
_NAMESPACES = {"mapping", "wiki"}
_ALLOWED_KINDS = {"mapping": {"mapping_change"}, "wiki": {"wiki_document"}}
```

文献 agent 的预设按 `namespace: "wiki"` + `kind: "wiki_document"` 写，并写进 `draft-writer` 的 instruction。`submitted_by` 由草稿箱的 MCP 传输层从 token 注入（`main.py:52-54` 会覆盖客户端传入的值），agent 不需要也无法自己指定。

## 五、通知：agent 发，`dedupe_key` 由 runtime 注入

`send_notification` 的必填项是 `notification_id` / `dedupe_key` / `notification_kind` / `recipients` / `subject` / `body` / `related` / `schema_version`。收件人是 `{"principal_id": ...}` 形状，由 email-service 的 `RegistryRecipientResolver` 调 Registry 的 `get_principal_contact` 解析成邮箱。

分工：**查 owner 属于 agent（领域知识），`dedupe_key` 属于 runtime（幂等控制）。**

- `mapping-reader` 用 `get_formal_mapping` 取当前正式图，找 TaskNode 文档的 `task_owner_id`（该字段在 `candidate_submission.py` 的 TaskNode 必填清单里，`dashboard_source.py:72` 也在读）；
- 收件人 = `[{"principal_id": task_owner_id}]`；
- `dedupe_key` 与第三节的 `idempotency_key` 同源（都由 `execution_id` 派生）。

### 服务端会拒的四种写法（逐条实测）

`email_service/service.py:572-596` 的 `_content_problem` 是硬校验：

1. **`notification_kind` 必须在白名单里。** `CONFIGURED_NOTIFICATION_KINDS`（`service.py:33-47`）共 13 个值，**没有** `task_agent_run_finished`。本票用 **`draft_ready`**——语义正好是「草稿已就绪待审」。若确实需要新种类，必须先在中央侧改配置或由 `SCIWEAVE_EMAIL_KIND_ALLOWLIST_JSON` 按 caller 单独放行，不能假设它可用。
2. **`schema_version` 必须是字符串 `"1"`**，不是整数 `1`（`intent.get("schema_version") != "1"` 直接判不合法）。
3. **`related` 必须是对象**（`isinstance(intent.get("related"), dict)`），空对象可以，`null` 或字符串不行。
4. **`subject` ≤ 200 字符、`body` ≤ 4000 字符，且两者都不允许 HTML 标记与禁用控制字符；`dedupe_key` 非空；`recipients` 非空且每项 `principal_id` 非空。**

`notification_id` 由 agent 自己生成；`related` 里放 `{"execution_id": ..., "task_node_id": ...}`，让通知可回溯到具体一轮执行。

**已知风险：** `ai4-dp9t`（open，hanjiang）正在修「Registry 的三个永久错误码全被压成 `registry_unavailable`」。在它修好之前，通知失败看不出真实原因，本票侧只能如实记 `notification_failed`，**不做重试风暴**。

## 六、`allowed_mcp_resources` 要能真的变成 fast-agent 的 MCP 配置

`config.py` 的 `workflow_to_fast_agent_input()` 已经能把 agent 的 `allowed_mcp_resources` 转成 `{"servers": [...]}`，但 `fast_agent_runtime.py:168` 生成的 `fast-agent.yaml` 只有两行：

```yaml
compaction:
  auto: false
session_history: true
```

**一个 MCP server 都没配**，所以 agent 手里没有任何 MCP 工具。需要把 `libs/mcp-libs/*/mcp.json` 的 `transport` / `endpoint.url_env` / `environment` 翻译成 fast-agent 的 `mcp.servers.<name>` 段，且**只注入该 agent 声明的那几张卡**。

当前卡片里 `draft-buffer` 与 `email-service` 都是 `transport: streamable-http` + `endpoint: {url_env: DRAFT_BUFFER_MCP_URL}` 这种形状，`sciencepal` 是 `endpoint: None`，`local-literature` 是 `transport: stdio`——三种形态都要覆盖，缺 `url_env` 对应环境变量时应当**报错而不是静默跳过**。

## 七、单 agent 最小样例

除文献工作流外，再给一个单 agent 预设（`libs/agent-libs/` 之外的独立 agent 定义），用于「我就想要一个能收活、能写草稿的 Task Agent」这种最朴素的用法，也作为研究员改写的起点。

## Acceptance Criteria

- [ ] `WorkflowDefinition` 新增 `plan_type`（`full` / `iterative`）与 `plan_iterations`（正整数）两个字段，`workflow_to_fast_agent_input()` 透出；未写时按 fast-agent 默认（`full` / 5）。
- [ ] YAML 里出现未声明的键时报 `unknown_field`，不再静默丢弃；补测试覆盖 workflow 段与 agent 段各一例。（若与 `ai4-4r0h` 的实现重叠，以先落地者为准，后落地者只补差额测试。）
- [ ] `libs/workflow-libs/literature-agent.yaml` 含四个子 agent 与一个编排器，全部通过 `load_workflow_yaml` 校验（含 `version: 1.0.0` 与 `summarizer`）。
- [ ] 四个子 agent 各自的 `allowed_mcp_resources` 与第二节的表逐条一致；编排器为空。
- [ ] 生成 `fast-agent.yaml` 时按 `allowed_mcp_resources` 注入 `mcp.servers`，未声明的卡不注入；三种 `transport` / `endpoint` 形态各有测试；缺失 `url_env` 指向的环境变量时报错。
- [ ] `final_writer` 由 runtime 在编排结束后调用一次，不由 plan 决定；补测试：编排器 plan 里不含 `draft-writer` 时它仍被调用。文档写明四类工作流都会多调这一次，且 Router / Agents as Tools 的这次调用不产出新信息，仅为草稿署名格式。
- [ ] `draft-writer` 的 instruction 规定只输出 `{"draft_id": ..., "summary": ...}`；runtime 用 `json.loads` + UUID 校验解析，落库标记 `agent_reported` 并由 `query_execution` 返回。
- [ ] 解析失败或非 UUID → `failed` + `draft_id_missing`，不写伪造的 `draft_id`；补测试覆盖「agent 返回纯文本」「返回非 UUID 字符串」两例。
- [ ] `create_draft` 预设用 `namespace: "wiki"` + `kind: "wiki_document"`（枚举来自 `buffer/src/draft_buffer/service.py:12-13`）。
- [ ] 通知 `notification_kind` 用 `draft_ready`，`schema_version` 为字符串 `"1"`，`related` 为对象并含 `execution_id` / `task_node_id`，`subject` ≤ 200、`body` ≤ 4000 且不含 HTML；补测试对 `_content_problem` 的四条硬校验各覆盖一例。
- [ ] 通知的 `dedupe_key` 由 runtime 注入（与 `idempotency_key` 同源）；收件人取 `task_owner_id`；email-service 不可用时只记 `notification_failed`，不重试。
- [ ] 单 agent 最小样例可加载、可跑通 passthrough 路径。
- [ ] 端到端测试在**无真实 API key** 的前提下跑通：使用 passthrough runtime + 假 MCP，验证「入队 → 编排 → 写草稿 → 通知」的状态流转与 `draft_id`（含 `agent_reported` 标记）落库。
- [ ] 文档说明每个 agent 的职责、挂哪些卡、为什么这么切；注明 `Orchestrator` 与 `Parallel` 不能挂 MCP 这一 fast-agent 约束及其来源。
- [ ] runtime 全量测试通过；`compileall` 与 `git diff --check` 通过。

## Blocked by

- [ai4-cxnm](ai4-cxnm.md)：`literature-searcher` 依赖的 `literature-search` 卡与服务。
- [ai4-tj83](ai4-tj83.md)：只读卡的工具面必须先收敛，否则注入给 agent 的是带写正式域能力的全集。
- [ai4-4r0h](ai4-4r0h.md)：`WORKFLOW_LIBS_PATH` 未实现，工作流加载不出来；且 `libs/workflow-libs/` 内 agent 名必须全局唯一，否则本票的预设与示例样板同目录加载会冲突。
- [ai4-4zjz](ai4-4zjz.md)：`subscriber` 现在自己装配 `BufferMCPDraftWriter` 并持有草稿箱凭据。不先把它移出订阅端，本票第三节的「agent 写草稿」就会和订阅端的直写并存，同一轮执行写出两份草稿。

## Not in Scope

- 不实现 `literature-search` 服务本身（`ai4-cxnm`）。
- 不改卡片工具面（`ai4-tj83`）。
- 不改草稿箱服务端的 `_authorize_namespace` 或新增按 `idempotency_key` / `source_execution_record_id` 查询的工具——那属于中央侧，本票按现有协议用 `agent_reported` 落地。
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

**2026-10-27 复核修订（Frank Qi）**

> *This was generated by AI during triage.*

同日 grill 复审推翻并修正了本票四处，逐条记明依据：

1. **`draft_id` 从「runtime 反查」改为「agent 结构化回传」。** 原第三节写的 `idempotency_key` → `list_drafts` 反查有实现路径错误：草稿箱 `_authorize_namespace`（`buffer/src/draft_buffer/service.py`）要求调用者在该命名空间 `reviewers` 中，而套件 token 映射出的 actor 就是 `submitted_by`。实测提交者调 `list_drafts` / `read_draft` 均返回 `forbidden`；且 `list_drafts` 入参只有 `namespace` / `status` / `submitted_by`，没有按 key 过滤的能力。改走 agent 自述 + UUID 校验 + `agent_reported` 标记，代价已在第三节写明。
2. **YAML 示例补 `summarizer`。** `config.py` 的 `load_config` 把 `summarizer` 设为所有类型必填，原示例缺它，实测报 `[missing_summarizer]`。
3. **`plan_type` / `plan_iterations` 原来写了但不生效。** `WorkflowDefinition` 无这两个字段，实测 `hasattr(w, 'plan_type')` 为 `False`，转换层也不透出。原第二节把它们当成已生效来写，属于错误；现改为由本票扩字段，并把未知键静默忽略升级成 `unknown_field`。
4. **`notification_kind` 用了不存在的值。** 原文写 `task_agent_run_finished`，但 `email_service/service.py:33-47` 的 `CONFIGURED_NOTIFICATION_KINDS` 里没有它。改用 `draft_ready`，并补齐 `schema_version == "1"`、`related` 为对象、`subject`/`body` 长度与 HTML 限制四条硬校验。
5. **`final_writer` 的措辞纠正。** 原文说「由 runtime 在编排结束后确定性调用」像是要新增的行为，实际 `workflows.py:57-58` 已经是这样。真正要处理的是四类都无条件多调一次，结论改为保留并说明理由。
