---
id: ai4-derq
status: closed
deps: []
links: [ai4-u9gj, ai4-3zxu]
created: 2026-10-27T13:35:41Z
type: bug
priority: 2
assignee: Frank Qi
tags: [message-envelope, central, protocol, correctness]
---
# 信封格式三分叉：文档称权威的分层信封零调用方，线上跑的是另一份手写 dict

`docs/data-flow/message-queue.md:69-90` 规定所有 Redpanda 业务消息使用统一信封，`shared/message-envelope/`（`ai4-3zxu`）是它的实现包。**线上没有任何一条消息经过它。**

## 一、四种形状

实测字段（不是读文档抄的，是把各生产者的真实 dict 跑出来的）：

| 出处 | 顶层字段 | 家族 |
| --- | --- | --- |
| `shared/message-envelope/`（包本身，不是生产者） | `message_id` `message_type` `schema_version`(int) `dedupe_key` `occurred_at` `published_at` `producer{service,instance_id}` `routing{partition_key,target_agent_id}` `payload` | 分层（权威候选） |
| `coordinator/src/coordinator/adapter_publisher.py:52-62` | `message_type` `mapping_domain_id` `task_node_id` `target_node_version_ref` `target_agent_id` `pending_handoff_id` `trigger_revision_id` | 扁平 A |
| `research-map/src/research_mapping/governance_events.py:137-146` | `event_id` `event_type` `schema_version`(**str** `"1"`) `mapping_domain_id` `occurred_at` `dedupe_key` `target{kind,id}` `payload` | 扁平 B |
| `research-wiki/src/llm_wiki/governance_events.py:127-136` | 同 B，但 `wiki_domain_id` 取代 `mapping_domain_id` | 扁平 B |
| `centre-agents/gateway/ingest/src/gateway_ingest/service.py:317-328` | `event_id` `event_type` `schema_version`(**int** `1`) `mapping_domain_id` `occurred_at` `dedupe_key` `target{kind,id}` `payload` | 扁平 B |

四个生产者里 `make_event_body` **零生产调用方**（只有 `tests/test_governance_consumer.py` 用它），所以线上实际只有三条消息在跑。

### 与 `payloads.py` 必填项逐条对齐

信封包的必填项分两层：信封必填（`Envelope` 的 9 个字段）与 payload 必填（`PAYLOAD_SCHEMAS`）。

| 信封必填字段 | 信封包 | 协调器 | map | wiki | ingest |
| --- | --- | --- | --- | --- | --- |
| `message_id` | ✅ | ❌ **缺** | ❌（有 `event_id`） | ❌（同） | ❌（同） |
| `message_type` | ✅ | ✅ | ❌（有 `event_type`） | ❌（同） | ❌（同） |
| `schema_version`（int） | ✅ | ❌ **缺** | ⚠️ 是 str `"1"` | ⚠️ str `"1"` | ✅ int `1` |
| `dedupe_key` | ✅ | ❌ **缺** | ✅ | ✅ | ✅ |
| `occurred_at` | ✅ | ❌ **缺** | ✅ | ✅ | ✅ |
| `published_at` | ✅ | ❌ **缺** | ❌ **缺** | ❌ **缺** | ❌ **缺** |
| `producer` | ✅ | ❌ **缺** | ❌ **缺** | ❌ **缺** | ❌ **缺** |
| `routing` | ✅ | ❌ **缺** | ❌ **缺** | ❌ **缺** | ❌ **缺** |
| `payload` | ✅ | ❌（业务字段在顶层） | ✅ | ✅ | ✅ |

| `task_handoff_ready` payload 必填 | 信封包 | 协调器 |
| --- | --- | --- |
| `mapping_domain_id` | ✅ | ✅ |
| `task_node_id` | ✅ | ✅ |
| `target_node_version_ref` | ✅（无形状规则） | ✅（string，与文档的对象形状冲突） |
| `target_agent_id` | ✅ | ✅ |
| `pending_handoff_id` | ✅ | ✅ |
| `trigger_revision_id` | ✅ | ✅ |
| `upstream_source_refs` | ✅ + 必须 array | ❌ **不发布**（`service.py:535` 算出后丢弃） |
| `dependency_edge_version_refs` | ✅ + 必须 array | ❌ **不发布**（`service.py:539`） |
| `executor_ref_snapshot` | ✅ + 必须 array | ❌ **不发布**（`service.py:545`） |
| `task_text` | ❌ **未定义** | ❌ 无此字段（链路源头也没有，见第三节 A6） |

| 治理事件 payload 必填 | 信封包 | map | wiki | ingest |
| --- | --- | --- | --- | --- |
| `formal_revision_published` → `mapping_domain_id` + `formal_revision_id` | ✅ | ⚠️ id 在 payload、domain 在顶层 | ❌ **无 mapping_domain_id** | ✅（`make_event_body`） |
| `candidate_created` → `mapping_domain_id` + `candidate_id` | ✅ | ❌ 发的是 `submission_id` | ❌ 同 | ❌ 同 |

最后一行是个独立的坑：`payloads.py` 要 `candidate_id`，map/wiki 两个发布者都发 `submission_id`（`governance_events.py:66-72`），而 ingest 的消费端 `service.py:278` 写的是 `event.payload.get("candidate_id") or event.payload.get("submission_id")`——**消费端在两年前就知道会分裂，用 `or` 糊住了，协议定义一直没改**。实测：

```
validate_payload("candidate_created", {"submission_id":"s-1","proposal_id":None,"candidate_head":None,"domain":"mapping"})
  → missing required field(s): mapping_domain_id, candidate_id
```

信封包零调用方，实测：

```
$ grep -rn "message_envelope" --include=*.py --include=*.toml --include=*.yaml sci-weave/ \
    | grep -v '\.venv' | grep -v pycache | grep -v 'message-envelope/' | grep -v tests
(空)
```

连 `pyproject.toml` 里都没有任何项目把它列为依赖。

## 二、后果

**没有一个消费者能读所有生产者**，而且分裂出来的每个洞都会静默失败。逐条实测：

**1. 信封包读不了任何一个真实生产者。**

```
decode(coordinator 的 dict) → EnvelopeFormatError: message_id must be a non-empty string
decode(research-map 的 dict) → EnvelopeFormatError: message_id must be a non-empty string
```

**2. 协调器把已经算好的字段扔掉了。** `service.py:535/539/545` 和 `861/865/868` 算出 `upstream_source_refs`、`dependency_edge_version_refs`、`executor_ref_snapshot`，`adapter_publisher.publish()` 一个都不往外发。实测发布出去的就是 7 个字段。

**3. 就算补上也会崩，因为形状不对。** 这三个字段在 `HandoffReadyMessage` 里是 `tuple[tuple[str, str], ...]`，落成 JSON 是 `[["T0","v0"]]`；文档与消费端期望的是 `[{"logical_id":"T0","version_id":"v0"}]`。`payloads.py` 的 `ARRAY_FIELDS` 只检查「是不是 list」，所以 `[["T0","v0"]]` 会**一路通过校验**，然后在消费端 `.get("logical_id")` 上炸。这是信封包自己的洞，不是生产者的。

**4. `wiki_domain_id` 不是 `mapping_domain_id` 改名。** `research-wiki/src/` 里 `mapping_domain_id` 出现 **0 次**，`research-map/src/` 里 `wiki_domain_id` 出现 0 次。两个域是两套注册表，wiki 版本发布时不存在可填的 mapping 域。实测：

```
validate_payload("formal_revision_published", wiki 的 payload)
  → missing required field(s): mapping_domain_id
```

**5. 这条不是「将来会坏」，现在就是坏的。** 把 wiki 的真实信封喂给协调器的 `GovernanceEventConsumer.handle()`：返回 `None`，`on_formal_revision_published` 一次都没被调用。把同样的消息换成 `mapping_domain_id` 就路由成功。

不过要更正一个我原本要下的结论：**不能把这归因于信封格式**。`research-wiki/src/main.py:133` 构造 `WikiManagementService` 时根本没传 `governance_events=`，于是 `management.py:122` 落回 `NoopGovernanceEventPublisher()`——wiki 的治理事件**连发都发不出去**，`KafkaGovernanceEventPublisher` 在 wiki 侧只在测试里被实例化过（`research-wiki/tests/test_governance_events.py:9`），`.env.example` 里也没有 `SCIWEAVE_WIKI_KAFKA_BOOTSTRAP`（map 有 `SCIWEAVE_MAPPING_KAFKA_BOOTSTRAP`，`research-map/.env.example:33`）。

所以 wiki 下发不了游交接有**两个独立成因**：发布端没接线（比格式更早的问题），以及就算接上了消费端也会因为 `mapping_domain_id` 丢掉它。第二个是本票的范围，第一个不是——它属于「领域发布者零生产调用方」，与 `ai4-3zxu` 交付的包无关。这条要单独记：**修好格式不代表 wiki 的事件会出现**。

（`research-map` 侧没这个问题：`research-map/src/main.py:89` 传了 `create_governance_publisher(config.governance_kafka_bootstrap)`。）

**6. `task_completed` 文档与消费端读的不是同一个字段，而且没有生产者。** 文档式 payload（`payloads.py:42-50`，含 `completed_version_ref`）能通过校验，但 `adapter_events._handle_task_completed` 只认 `node_version_ref` / `task_node_version_ref` / `target_node_version_ref` → 返回 `None`，下游不解除。而且**全仓库没有任何代码发布 `task_completed`**（只有消费端、schema 和 `service.on_task_completed`），文档写的那条「解除下游完成条件」路径在生产上不可达。

生产者的缺席是**有据可查的**，不是漏了：`ai4-te1v:96` 明确裁决「`task_completed` 由 Task Agent Worker 在 ExecutionRecord 保存 `completed` 且草稿箱写入成功后生产」。但套件的 worker（`runtime/` + `service-template/worker/`）**没有任何 Kafka 生产者代码**——它在端侧跑，`grep producer` 只能找到注释。所以这条链缺的不只是格式对齐，是**端侧没有发布通道**：一个跑在研究员笔记本上的 Worker 要往中央 Redpanda 写一条消息，需要出站凭据、topic 授权和失败重试语义，这些都不存在。这是本票**范围之外**的第二个洞，但必须写下来，否则会以为「修好字段就好了」。

再加上格式层面：文档定义 `completed_version_ref`，消费端读三个别的名字，两边的字段名没有一个对得上。修字段只是必要条件。

**7. 字段名四家不一致。** `task_node_id`（信封包 + 协调器）vs `target_node_id`（`message-queue.md:313`、`message-delivery-recovery.md:37-38`）。套件订阅端按 `task_node_id` 取，实测喂文档的 `target_node_id` 直接抛 `EnvelopeError`。

**8. 连文档自己的例子都过不了信封包的校验。** 把 `message-queue.md:306-324` 的 payload 原样送进 `validate_payload("task_handoff_ready", …)`：

```
→ missing required field(s): task_node_id
```

所以这不只是「文档 vs 代码」分叉，是**文档 / 信封包 / 三个生产者四方分叉**。

**9. 分区键也对不上，而且这次是代码错。** 文档说 `target_node_id`（`message-queue.md:65`、`:350`、`message-delivery-recovery.md:37`），协调器实际发 `f"{task_node_id}:{target_node_version_ref}"`。信封包的 `routing.partition_key` 没有任何生产者对应实现。

这里**文档是对的，协调器是错的**：分区键的作用是把需要保序的消息放进同一分区，而同一 TaskNode 的不同版本恰恰是最需要保序的一对；用复合键恰好把它们劈到两个分区。这个复合键还有第二个危害：它是套件订阅端 `task_node_id()` 绝不能回退到 key 的唯一原因（key 里塞了版本号，回退会把 `"T1:cv-2"` 当成节点 id 送进草稿箱、执行记录和租约，见 `ai4-u9gj` 的原始 bug）。分区键修对之后这个陷阱才消失。协调器那一行归阶段 1。

**10. `schema_version` 三态。** 信封包要求 int；map/wiki 发字符串 `"1"`；ingest 发 int `1`；协调器**什么都不发**。而且 ingest 用 `int(x) != 1` 把两种都收下，套件订阅端用 `!=` 只收 int——同一个缺失字段，两个消费者给出两个相反的「接受」语义。

这也是 `ai4-u9gj` 那张票的初版结论出错的地方：我按文档认定「分层信封是权威格式」，据此复现出一个不存在的 bug。文档与实现分叉到这个程度，会持续误导后续判断。

## 三、裁决

**唯一权威格式：信封包的分层形状。** 理由是它有 `validate()`、有 `PAYLOAD_SCHEMAS`、且不携带 Kafka 客户端，迁移只需改生产者而不需要重新发明协议。但裸用不行，需要七条修正：

| # | 修正 | 代价 |
| --- | --- | --- |
| A1 | 治理事件类的 payload 允许 `wiki_domain_id` 作为 `mapping_domain_id` 的**并列替代**（不是改名） | 校验器加一个 `or` + 一行文档；避免 192 处改名和一个假断言 |
| A2 | `schema_version` 保持 **int 且必填**；map/wiki 各改 2 处 `"1"`→`1` | 4 行；同时删掉 ingest 的 `int()` 强制转换，否则它继续掩盖分裂 |
| A3 | 字段名用 `task_node_id`，**文档改** | 0 行代码；文档 2 处 |
| A4 | `target_node_version_ref` 是**纯版本号字符串**；两个 `*_refs` 数组的元素是 `{"logical_id","version_id"}` 对象，协调器发布时做投影 | 协调器加投影函数；信封包补元素形状校验（补洞 #3） |
| A5 | `task_completed` 统一用 `completed_version_ref`；消费端先读它，其余三个名字作一个窗口的兼容回退 | 消费端 3 行 |
| A6 | `task_handoff_ready` **新增必填 `task_text`** | 见下 |
| A7 | `candidate_created` 的候选标识统一为 `candidate_id`；map/wiki 发布者的 `submission_id` **保留**（它是提交单 id，不是候选 id），另加 `candidate_id` | 两个发布者各 1 行；ingest 的 `or` 回退留一个窗口 |

**A6 是最贵的一条，也是唯一一条动到拓扑的。** `TaskNodeDoc` 只有 4 个字段（`task_node_id` `version_id` `executor_refs` `task_owner_id`），实测把 map 的完整 TaskNode 文档（含 `title`、`objective`）喂进 `_build_snapshot()` 之后：

```
TaskNodeDoc fields: ['task_node_id', 'version_id', 'executor_refs', 'task_owner_id']
text survived?     : NONE
```

也就是说任务文本在协调器这一层就被丢掉了，跟 `adapter_publisher` 丢 refs 是同一类问题。`payloads.py` 里没有 `task_text` 是**故意的**：协议层从未裁决过它该不该在消息里。套件订阅端的 `TASK_TEXT_FIELDS`（5 个候选名）就是这个空洞的记录。本票的裁决是：**该在**。不放进消息，端侧 agent 永远只能拿到一个节点 id，`worker_shell.task_instruction` 里那句「只收到了节点引用」就成了永久状态。落地要两件事：`TaskNodeDoc` 长出 `title`/`objective`（或一个合成好的指令串），`PAYLOAD_SCHEMAS` 加 `task_text`。存储侧归 `ai4-1e9e`。

**A7 的取舍**：`submission_id` 是「哪一次提交」，`candidate_id` 是「哪个候选」。一个提交可以产出多个候选，所以 `submission_id` 在语义上不能当 `candidate_id` 用。但两个发布者现在把后者当前者使，且 ingest 用 `or` 兜住了。裁决是**加字段而不是改名**：改 `submission_id` 会动到 map/wiki 已经落库的字段与既有消费者的读取路径，而它本身没错，只是不够。

## 四、迁移方案

原则：**消费者先行，且每个消费者在一个发布里同时接受两种形状**。这样破窗期为零，不需要停服对齐。

| 阶段 | 改谁 | 消费者怎么读 |
| --- | --- | --- |
| 0 | 信封包加 `decode_legacy()` / `accepts_legacy()`，并补 A1–A7 的校验规则 | 一个读入口吃两种形状；**删除条件写进 docstring**：阶段 1–4 全部上线一个发布后删 |
| 1 | **协调器 publisher**（先做，因为它的消费者已经容忍） | 套件订阅端 `field()` 已经是 payload 优先、顶层兜底，`routing_field()` 先看 `routing` —— 实测不用改就能读分层信封 |
| 2 | **协调器 `GovernanceEventConsumer`**（消费者先改） | 同一次提交里 `message_type` 和 `event_type` 都读，前者优先 |
| 3 | map / wiki publisher → 分层 | 上一步已经能读，所以生产者随便什么时候上 |
| 4 | `centre-agents/gateway/subscriber/src/gateway_subscriber/service.py:46` | 现在只读 `target.id`，真实交接必抛 `ValueError: id is required`；改成 `payload.task_node_id` → `target.id`。**这一步无论格式怎么定都得做** |
| 5 | 删 `decode_legacy` 与各消费端的兼容回退 | 条件：阶段 1–4 均已发布一个版本 |

顺序的理由：协调器换格式时它的下游（套件订阅端）**已经**是容忍读取，所以阶段 1 单独上线不破窗；map/wiki 换格式时下游是协调器，所以必须先做阶段 2。反过来的顺序在任何一步都会有一个发布窗口读到读不懂的消息。

阶段 4 那个消费者现在自带的测试 fixture（`tests/test_subscriber.py:74-96`）造了**第五种**形状（`event_id` + `event_type` + `target.kind/id` + payload 里的单数 `dependency_edge_version_ref`），没有一个生产者发这个。修它的时候测试要按 `adapter_publisher.py` 的真实输出重写，不是把断言改成通过。

**不建议**让每个消费者学两种形状（套件订阅端现在就是这么干的：跨位置按字段名找）。它把「协议没定」的成本摊到 N 个消费者，且每个新消费者都要重新踩一遍。`decode_legacy()` 把这份成本收在协议包里一处。

## 五、`schema_version` 缺失的语义

**定必填，定 int。** 代价和收益都摆在明面上：

| 选项 | 代价 | 判断 |
| --- | --- | --- |
| 缺失即接受 | 现在的状态。容忍式读取规则（「版本相同即可消费」）**无法执行**，因为没有可比的版本号——这正是四种格式能活到今天的机制 | 否决 |
| 缺失即拒绝 | 协调器立刻全部断流（它不发这个字段） | 否决，除非同一次发布里补上 |
| **必填 + 生产者补齐** | 协调器 1 行、map/wiki 4 行、ingest 删掉 `int()` 强制转换 | 采纳 |

「缺失即接受」还有个隐性代价：两个消费者对同一个缺失给出相反语义（ingest 的 `int(x)` 把 `"1"` 和 `1` 都收下，套件订阅端只收 `1`）。这种「各自的宽容」比明确的严格更难排查。

## 六、文档对齐（已做）

AC #4 允许两条路：「改成与实际一致」或「加显著标注说明尚未落地」。**两条都做了，但分工不同**：标注负责说清「这不是现状」，改字段负责让目标格式自洽到可被校验。

`docs/data-flow/message-queue.md`：

1. `:69` 「消息信封」标题下加引用块警示：目标格式、尚未落地、信封包零调用方、四方不一致、迁移完成前不要按本节写新消费者、指向本票。
2. `:314` `target_node_id` → `task_node_id`（与信封包、协调器一致）。
3. `:315` `target_node_version_ref` 由 `{logical_id, version_id}` 对象改成纯版本号字符串（与协调器一致）——**这是有争议的一条**，见下。
4. `:65`、`:350` 分区键由 `target_node_id` 改成 `routing.partition_key = task_node_id`，并写明理由（同节点多版本必须同分区才能保序）。

关于第 3 条要留个记号：文档原来把 `target_node_version_ref` 写成对象，**可能比协调器的字符串更接近设计意图**（`message-queue.md:164` 与 `:394` 都在讲「正式化后才有版本引用」，对象形状能承载 `logical_id` + `version_id` 两个事实）。我改成字符串是为了让示例能通过 `validate_payload()` 并与当前协调器一致，也就是**向现状对齐而不是向意图对齐**。`payloads.py` 对这个字段没有形状规则，所以两种都能通过校验——这意味着这里的选择是开放的，实施切片时应当连同 `dependency_edge_version_refs` 的元素形状一起重新裁决（A4），而不是默认沿用字符串。

`docs/data-flow/message-delivery-recovery.md:29-46`：字段清单同样加「目标格式，尚未落地」指针，`routing.partition_key` 改 `task_node_id`，并补上漏掉的 `payload.dependency_edge_version_refs`（它一直是必填，文档里却缺）。

验证：改后的示例 payload 送进 `validate_payload("task_handoff_ready", …)` **通过**（改前 `missing required field(s): task_node_id`）。

**残留风险，必须记清楚**：改完之后 `message-queue.md` 的示例**仍不代表任何生产者的实际输出**——协调器不发 `message_id`/`schema_version`/`routing`/`producer`，`payload` 里也缺三个 ref 数组。文档现在描述的是「裁决后的目标格式」，不是「线上正在发的东西」。这正是警示块存在的理由；迁移完成后应当删掉警示块，而不是删掉字段。

**不在本票范围**：实际改任何生产者或消费者。实施要拆成垂直切片，每片一张票（上表 6 个阶段至少 4 张）。

## Acceptance Criteria

- [x] 一张对照表列出全部四个生产者的真实信封字段，与信封包 `payloads.py` 的必填项逐条对齐，标出哪边缺什么。
- [x] 给出迁移方案：先改谁、破窗期多长、旧消费者怎么读新消息、新消费者怎么读旧消息。
- [x] `schema_version` 缺失时的语义有明确结论并说明代价。
- [x] `docs/data-flow/message-queue.md` 的信封章节与实际一致，或加显著标注说明尚未落地。
- [x] 结论回写到 `ai4-u9gj`（它按真实生产者取字段，本票若改了格式需要跟进）。

## Notes

**2026-10-27 建档（Frank Qi）**

> *This was generated by AI during triage.*

身份核对：assignee `Frank Qi`、分支 `feature/frank-qi`、`git config user.name=Frank Qi`。

发现于 `ai4-u9gj` 的复核过程。这不是 `ai4-u9gj` 的范围内能修的：那张票只需让套件订阅端吃下**真实生产者现在发的东西**，而本票问的是「真实生产者应该发什么」。

优先级定 P2 而非 P1：当前演示链路（`humans/competition/demo-script.md`）不经过 Redpanda，赛事截止前不阻塞。但它是套件接入中央服务的真实阻塞项，`ai4-v869` 的公网 MCP 对接完成后会立刻撞上。

与 `ai4-3zxu` 不重复：那张票是「实现信封包」，已 closed，交付的包质量没问题；本票是「实现了没人用」。

**2026-10-27 裁决完成（Frank Qi）**

> *This was generated by AI during triage.*

全部五条 AC 已勾。核心结论：权威格式取信封包的分层形状 + 七条修正（A1–A7），迁移按「消费者先行」六阶段，破窗期为零；`schema_version` 定必填 int。

过程中的四条事实值得单独记，因为它们改变了「这是格式问题」的初始判断：

1. **不是纯格式问题。** wiki 的 `formal_revision_published` 到不了协调器，一半原因在格式（`wiki_domain_id` vs `mapping_domain_id`），另一半在 `research-wiki/src/main.py:133` 根本没注入 publisher、落回 `NoopGovernanceEventPublisher()`。修格式不会让 wiki 的事件出现。
2. **协调器在丢自己算好的数据。** `service.py:535/539/545` 算出三个 ref 数组，`adapter_publisher` 一个都不发。即使发了，形状也从 `tuple[tuple[str,str],...]` 落成 `[["T0","v0"]]`，而 `ARRAY_FIELDS` 只检查「是不是 list」，错误形状会通过校验然后在消费端炸。信封包自己的洞。
3. **任务文本从链路源头就不存在。** `TaskNodeDoc` 只有 4 个字段，`_build_snapshot()` 丢掉 `title`/`objective`，`payloads.py` 也从未定义 `task_text`。套件订阅端的 5 个候选字段名是这个空洞的症状，不是修法。
4. **`task_completed` 缺的不是字段，是通道。** `ai4-te1v:96` 定的是「Task Agent Worker 发布」，但套件 worker 跑在端侧、没有任何 Kafka 生产者代码，也没有出站凭据/topic 授权/重试语义。这超出本票范围，需要单独一张票。

改动落在 4 个文件：`.tickets/ai4-derq.md`（本票）、`.tickets/ai4-u9gj.md`（后续跟进三条）、`docs/data-flow/message-queue.md`（警示块 + 3 处字段修正）、`docs/data-flow/message-delivery-recovery.md`（警示指针 + 补 `dependency_edge_version_refs`）。

验证：修正后的示例 payload 送进 `validate_payload("task_handoff_ready", …)` 通过（改前 `missing required field(s): task_node_id`）；`git diff --check` 干净。本票**不含代码改动**，没有测试可跑。
