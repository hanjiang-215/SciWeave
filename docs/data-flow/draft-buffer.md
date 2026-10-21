# 中央草稿箱（Draft Buffer）

尚未成为领域候选的内容放在这里，由人审核。计划中对应 `sci-weave/centre-control/buffer`，目前只有一行说明。

本文件是 2026-10-21 讨论的设计记录，不是已发布的规格。与既有工单冲突之处在第 8 节单列。

## 1. 它是什么

中央服务器上一个共享的草稿服务，保存还没有进入任何领域候选分支的原始内容：

- Research Mapping 的路线变更草稿；
- LLM-Wiki 的文档与资源引用草稿。

它不做这些事：不保存候选版本或正式版本正文；不判断科研内容对错；不写领域存储；不发起执行；不保存执行过程状态。

> 修订（2026-10-21）：删去「Task Agent 的声明式设计稿」。Task Agent 改由研究员端侧自持，其定义与代码留在研究员的仓库，不进入草稿箱。

## 2. 一个库，两个命名空间

存储用 TerminusDB，一个数据库 `sciweave_draft_domain`：

| 数据库 | 命名空间 | 内容 | 审核人 | 通过之后 |
| --- | --- | --- | --- | --- |
| `sciweave_draft_domain` | `mapping` | 路线变更草稿 | 任务节点负责人 | 人调用 Mapping 管理 MCP 写入候选分支 |
| 同上 | `wiki` | Wiki 文档与引用草稿 | Wiki 负责人（Curator / Resource Owner / 文档负责人） | 人调用 Wiki 管理 MCP 写入候选分支 |

两个命名空间共享一个库的理由：同一类领域内容、同一套一审角色、同一个下游动作（写入候选分支）。

> 修订（2026-10-21）：原设计为两个数据库、三个命名空间，其中 `sciweave_draft_task_agent` 与命名空间 `task_agent_design` 随端侧自持一并删除。原文保留于版本历史。

命名空间是**文档上的一个字段**，不是库、不是目录。审核人不是每份草稿各填一次，而是**命名空间配置记录上的字段**，因为审核人随团队变化，不随草稿变化。

## 3. 文档模型

TerminusDB 没有文件夹，只有类与文档 ID。因此：

- 类 `Draft`：一份草稿的头部事实。
- 类似 `NamespaceConfig`：一个命名空间的配置，含审核人。

`Draft` 的字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `draft_id` | string | 稳定业务 ID，不由标题派生 |
| `namespace` | string | `mapping`、`wiki` |
| `kind` | string | 领域内细分，例如 `mapping_change`、`wiki_document` |
| `title` | string | 供人识别；不参与关联 |
| `submitted_by` | string | 提交者 principal id |
| `submitted_at` | string | ISO 8601 |
| `status` | string | 见第 4 节 |
| `base_formal_revision_id` | string，可空 | 草稿内容所依据的正式版本 |
| `source_task_node_id` | string，可空 | 弱引用，来源任务节点 |
| `source_execution_record_id` | string，可空 | 弱引用，来源执行记录 |
| `payload` | `sys:JSON` | 完整正文，按 `kind` 解释 |
| `submitted_commit` | string，可空 | 提交审核时固定的 TerminusDB Commit |
| `reviewer_id` | string，可空 | 提交时从命名空间配置解析并留档 |
| `review_decided_at` | string，可空 | |
| `review_reason` | string，可空 | 驳回理由或通过说明 |
| `supersedes_draft_id` | string，可空 | 修订关系，不改写原草稿 |

正文用 `sys:JSON` 整段存放，不把 Mapping 节点、Wiki 文档、设计稿各自展开成一套 schema。理由：三类正文形状差异大，而草稿阶段的审核只需要人看得懂、系统能原样取回。已在本机固定容器上实测：嵌套对象、数组、中文写入后读回无损。

`@key` 必须用 `Random`。用 `Lexical` 时字段值里的 `/` 会被百分号编码，提交的 `@id` 与生成的 `@id` 不一致直接报错，带层级感的 ID 就写不进去。

## 4. 状态机

```text
drafting → submitted → under_review → accepted → promoted
                     └→ rejected → (修订后重新 submitted)

任意非 promoted 状态 → abandoned
```

- `drafting`：作者还在写，不进审核队列。
- `submitted`：已提交，固定当前 Commit 为 `submitted_commit`；之后正文仍可修改，但不影响本轮审核对象。
- `under_review`：审核人已打开，避免两人同时审同一份。
- `accepted`：审核通过。**不产生候选分支**，等待人调用领域 MCP。
- `rejected`：驳回并写明原因；重新提交是新的 `submitted_commit`，原草稿历史保留。
- `promoted`：领域候选已创建，草稿转只读。
- `abandoned`：作者或审核人放弃。

审核对象是 `submitted_commit`，不是「最新内容」。这正是选 TerminusDB 的主要理由：每次写入天然产生 Commit，固定一个 hash 就能说清「人当时看的是哪一版」，不需要另做快照表。

草稿箱不使用分支。分支是领域候选的机制，草稿只有一个线性历史。

## 5. 两道审核，谁审什么

| 阶段 | 输入 | 审核人 | 产出 |
| --- | --- | --- | --- |
| 一审 | 草稿箱里的 `submitted` 草稿 | 命名空间配置的审核人 | `accepted`，或驳回并说明原因 |
| 候选形成 | 已 `accepted` 的草稿 | 人（不是 Agent）调用领域管理 MCP | 领域 candidate branch 的第一个 Commit |
| 二审初步审核 | 候选分支 | 中央 Agent | 格式、引用、权限、依赖、基准版本、冲突、影响范围，必要时生成混合候选 |
| 二审 | 候选与中央 Agent 的预审材料 | Project Owner | 批准或驳回 |

要点：

- **中央 Agent 不进草稿箱。** 它的工作从候选分支存在那一刻开始，读的是领域管理 MCP 暴露的候选，不读草稿。
- **草稿的接纳只能由人写。** 中央 Agent 至多能读草稿，不能写 `accepted` 或 `rejected`。
- **转成候选是人调用 MCP。** 草稿通过后不会自动进候选；提交者或审核人用自己的 MCP 客户端调用领域管理 MCP，以草稿身份和固定 Commit 作为输入创建候选。这样「谁把内容推进了领域」在领域审计链里是可追的，而不是由一个后台服务代劳。
- **二审的对象是候选，不是草稿。** 所以候选分支的内容不需要回到草稿箱。

## 6. 接口

草稿箱对外只有一套 MCP，工具按命名空间鉴权：

| 工具 | 用途 | 谁能调 |
| --- | --- | --- |
| `create_draft` | 新建草稿，返回 `draft_id` | 项目成员、端侧 Agent |
| `update_draft` | 修改草稿正文或标题，`drafting`/`rejected` 可改 | 提交者 |
| `submit_draft` | `drafting` → `submitted`，固定 Commit | 提交者 |
| `list_drafts` | 按命名空间、状态、提交者过滤 | 有该命名空间读权限的人 |
| `read_draft` | 读头部与正文，可指定 `submitted_commit` | 有该命名空间读权限的人 |
| `review_draft` | `accept` 或 `reject` 并写理由 | 该命名空间配置的审核人 |
| `mark_promoted` | 记录已创建候选（候选标识与 Commit） | 执行推进的人 |

幂等：`create_draft` 与 `submit_draft` 带幂等键；`review_draft` 带幂等键，重复调用返回首次结论，不产生第二次决定。

存储层已验证的能力与限制：

- GraphQL 可按字段过滤，支持 `limit`、`offset`；**没有 `order_by`**，排序在服务层做。
- 手写 WOQL 的 JSON-LD 形状容易写错，实测多种写法都被拒；查询走 GraphQL 或官方客户端生成的 WOQL。
- 一次请求写多份文档只产生一个 Commit，可用于「一份草稿 + 一条审核记录」同事务落地（Approach 待实现时确认）。
- 权限有 Role/User 两级，可按库授予实例读写；两个命名空间同库，因此按命名空间授权需要在服务层校验，不能只靠库级权限。

## 7. 与执行提交的区别

端侧 `Execution Submission`（执行结果的待审提交）**不进草稿箱**。它留在 Gateway 的 SQLite，因为审核决定、审计事件和通知 outbox 必须在同一事务里写入；搬进 TerminusDB 会重新引入跨存储失败模式。它也不再叫 Buffer。

三个名字从此分开：

| 名字 | 指什么 |
| --- | --- |
| Draft Buffer（中央草稿箱） | 本文件描述的服务，存领域草稿与设计稿 |
| Merge Request Buffer | 正式化请求对象，引用已锁定的候选头，不承载正文 |
| Execution Submission | 端侧执行结果的待审提交，存在 Gateway SQLite |

## 8. 与既有决策的冲突

以下条目由不同负责人持有，本文件只记录冲突，不改写原票。

1. **`ai4-mjku` / `ai4-hkdz` 把 Buffer Submission 放在领域 SQLite。** 新模型里草稿在 TerminusDB 草稿箱，领域 SQLite 只从 Proposal 与 CandidateCommit 开始。需要决定：领域侧是否保留一条「由哪份草稿推进而来」的来源记录（建议保留，字段只存 `draft_id` 与 `submitted_commit`，不复制正文）。
2. **`ai4-xrxw` 的状态链 `received → owner_review → accepted → central_pre_review → candidate_created`。** 新模型里一审在草稿箱完成，`central_pre_review` 作用在候选上而不是提交上，`candidate_created` 由人调用 MCP 触发。这条链需要按新顺序重述。
3. **`ai4-wd5l` 的「Owner 接纳后创建领域草稿」。** 新模型是「草稿在先、候选在后」，顺序相反。该票已关闭，由票负责人决定是否重开。
4. **GLOSSARY 的 Domain Isolation「不得共享 Buffer」。** 新模型里 Mapping 与 Wiki 共用一个草稿库，隔离降级到命名空间与领域事务层面。术语表已加修订说明。
5. **`ai4-3nru`「不共享 Buffer」。** 同上，需要该票负责人确认新表述。

## 9. 尚未定

1. `mark_promoted` 由谁调用：推进候选的人顺手调第二次，还是领域管理 MCP 在创建候选后回调草稿箱。前者多一次人工操作，后者让领域服务反向依赖草稿箱。
2. 草稿箱是否需要跨命名空间的统一收件箱视图。同一库内可按命名空间过滤，服务层聚合两次查询即可，不再是跨库问题。
3. 草稿与候选之间是否需要强校验（候选内容必须与该草稿的 `submitted_commit` 一致）。若要求一致，领域 MCP 就得读草稿箱，等于把草稿箱变成领域依赖。
4. 参与者身份从哪来。当前只有本地开发令牌，没有人员目录。
