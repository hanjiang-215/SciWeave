---
id: ai4-5auy
status: open
deps: [ai4-t2wc]
links: [ai4-rlv6, ai4-w73z, ai4-he04, ai4-5z9e, ai4-oebi, ai4-8dgd]
created: 2026-10-24T15:20:01Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-fv1r
tags: [implementation, centre-control, mcp, permission, prereview, ready-for-agent]
---
# 收紧管理 MCP 的中央 Agent 开放面并补两个预审写工具

按「注册表登记中央 Agent 与其开放面」(ai4-t2wc) 定稿的工具白名单，把两套领域管理 MCP 的 `centre` 能力从「可调全部工具」收紧为「只读三组」 ，并新增两个只供中央 Agent 使用的预审写工具。

## Problem Statement

两套管理 MCP 现在把 `centre` 能力名挂在了几乎所有工具上。以 Mapping 为例：

```287:296:sci-weave/centre-control/research-map/src/research_mapping/management.py
_TOOL_CAPABILITIES = {
    "get_formal_mapping": _READ_CAPABILITIES,
    "list_candidates": _READ_CAPABILITIES,
    "list_reviewable_candidates": _READ_CAPABILITIES,
    "submit_candidate": _CANDIDATE_SUBMIT_CAPABILITIES,
    "preview_candidate": frozenset({"candidate_review", "centre"}),
    "record_review": frozenset({"candidate_review", "centre"}),
    "formalize_candidate": frozenset({"formalize", "centre"}),
    "reconcile_formalization": frozenset({"formalize", "centre"}),
}
```

`_READ_CAPABILITIES` 是 `{"read", "centre"}`，`_CANDIDATE_SUBMIT_CAPABILITIES` 是 `{"candidate_submit", "centre"}`。也就是说，只要给中央 Agent 一个 `centre` 凭据，它就能提交候选、发起审阅、推进正式版本——而这三件事都被 `ai4-t2wc` 与「中央 Agent 候选预审职能地图」(ai4-fv1r) 明确禁止。Wiki 侧同样，`decide_wiki_review`、`formalize_wiki`、`reconcile_wiki_formalization` 都带 `centre`。

同时，中央 Agent 唯一需要的两个写工具 `append_prereview_log` 与 `create_merged_candidate` 在两套 MCP 里都不存在。全仓库除 `ai4-rlv6`、`ai4-oz3s` 与 `centre-agents/README.md` 的描述外，没有任何实现。

## Solution

两个动作，都在两套领域管理 MCP 内完成，互不跨领域：

**一、摘除 `centre` 的写授权。** 从 `_TOOL_CAPABILITIES` 中移除 11 个工具对 `centre` 的授予，只保留 6 个读工具。`centre` 从此只表示「读全部候选与正式版本」。

**二、新增两个写工具与两个能力名。** `append_prereview_log` 追加预审报告或失效判定，`create_merged_candidate` 新建混合候选。两者各带必需的领域参数，能力名分别为 `prereview_log` 与 `merged_candidate`，与 `centre` 分开配置。

工具名用单数 + 领域参数，而不是分领域四名单数名（`append_mapping_prereview_log` 等）。理由：领域隔离已由「两套独立 MCP、两次独立调用」保证，工具名再分一次会让 `ai4-rlv6` 的工具清单与读工具的命名风格不一致。`ai4-rlv6` 与 `centre-agents/README.md` 的对应措辞需同步修正。

## Design

### 能力名与环境变量

两套 MCP 的 `_CAPABILITY_ORDER` 从五档扩为七档：

```python
_CAPABILITY_ORDER = (
    "read", "candidate_submit", "candidate_review", "formalize",
    "centre", "prereview_log", "merged_candidate",
)
```

`SCIWEAVE_MAPPING_CALLER_CAPABILITIES_JSON` 与 `SCIWEAVE_WIKI_CALLER_CAPABILITIES_JSON` 的校验逻辑不变（校验每个名字合法、存成 `frozenset`、不建继承）。中央 Agent 的配置需要三个名字：

```json
{
  "service:centre-agent": ["centre", "prereview_log", "merged_candidate"]
}
```

两个写工具的能力名分开，是为了让运维可以按需只给其中一个。三个名字共用一个 bearer token 是可以的——`ai4-t2wc` 要求分开的是工具面，不是凭据。

### 收紧后的工具表

**Mapping（research-map）**

| 工具 | 收紧后要求的能力名 |
| --- | --- |
| `get_formal_mapping` | `read` 或 `centre` |
| `list_candidates` | `read` 或 `centre` |
| `list_reviewable_candidates` | `read` 或 `centre` |
| `submit_candidate` | `candidate_submit`（**移除 `centre`**） |
| `preview_candidate` | `candidate_review`（**移除 `centre`**） |
| `record_review` | `candidate_review`（**移除 `centre`**） |
| `formalize_candidate` | `formalize`（**移除 `centre`**） |
| `reconcile_formalization` | `formalize`（**移除 `centre`**） |
| `append_prereview_log`（新增） | `prereview_log` |
| `create_merged_candidate`（新增） | `merged_candidate` |

**Wiki（research-wiki）**

| 工具 | 收紧后要求的能力名 |
| --- | --- |
| `get_formal_wiki` | `read` 或 `centre` |
| `list_wiki_candidates` | `read` 或 `centre` |
| `list_reviewable_wiki_candidates` | `read` 或 `centre` |
| `submit_wiki_candidate` | `candidate_submit`（**移除 `centre`**） |
| `preview_wiki_review` | `candidate_review`（**移除 `centre`**） |
| `create_wiki_merge_request` | `candidate_review`（**移除 `centre`**） |
| `decide_wiki_review` | `formalize`（**移除 `centre`**） |
| `formalize_wiki` | `formalize`（**移除 `centre`**） |
| `reconcile_wiki_formalization` | `formalize`（**移除 `centre`**） |
| `append_prereview_log`（新增） | `prereview_log` |
| `create_merged_candidate`（新增） | `merged_candidate` |

`_READ_CAPABILITIES` 保持 `{"read", "centre"}` 不变。`_CANDIDATE_SUBMIT_CAPABILITIES` 退化为 `{"candidate_submit"}`。

### append_prereview_log 的输入

按「预审报告的追加日志契约」(ai4-oz3s) 的字段表实现。最小输入：

- 领域标识（`mapping_domain_id` 或 `wiki_domain_id`，与读工具一致）；
- `candidate_id`、`candidate_head`、`base_formal_revision_id`；
- `rule_set_version`、检查项清单、`verdict`、`conflict_matrix`；
- 追加类型：新报告或失效判定（`head_moved` / `base_moved`）。

唯一键 `(candidate_id, candidate_head, rule_set_version)`。重复追加同一键返回首次结论并标记 `duplicate=true`，不产生第二行。`rule_set_version` 无法解析到规则文件时返回 `rule_set_missing` 并拒绝写入，不写一份无据可查的报告。

报告行只读：失效不改旧行，追加一条判定，当前有效报告由同一候选最新判定推出。

### create_merged_candidate 的输入

按「混合候选的生成与作者身份」(ai4-8dgd) 实现。最小输入：领域标识、来源候选 ID 列表、目标基准正式版本、混合后的内容。

约束：

- 只能新建，不改动任何已有候选；
- 作者记为全部来源作者；
- 来源作者对混合候选没有任何操作权；
- 不可二次混合——来源里含有混合候选时拒绝，返回稳定错误码。

### 审计

两个新工具均为写调用，按现有接口层账本规则走 `begin_call` fail-closed、`finish_call`。审计记录只含调用者、通道、服务、工具、目标对象标识、结果与耗时，不含报告正文、候选内容或完整入参。

不允许绕过：`append_prereview_log` 不写领域 AuditEvent，`create_merged_candidate` 不写正式版本。

## Acceptance Criteria

- [ ] `centre` 凭据调 `submit_candidate`、`preview_candidate`、`record_review`、`formalize_candidate`、`reconcile_formalization` 全部返回 `forbidden`
- [ ] `centre` 凭据调 `submit_wiki_candidate`、`preview_wiki_review`、`create_wiki_merge_request`、`decide_wiki_review`、`formalize_wiki`、`reconcile_wiki_formalization` 全部返回 `forbidden`
- [ ] `centre` 凭据仍可调两侧各 3 个读工具（`get_formal_*`、`list_*_candidates`、`list_reviewable_*_candidates`）
- [ ] `append_prereview_log` 在两个领域各可用，唯一键幂等，重复追加返回 `duplicate=true` 且不产生第二行
- [ ] `append_prereview_log` 在 `rule_set_version` 无法解析时返回 `rule_set_missing` 且不写入
- [ ] `append_prereview_log` 追加失效判定时不修改已有报告行
- [ ] `prereview_log` 与 `merged_candidate` 是两个独立能力名，只给其中一个时另一个仍返回 `forbidden`
- [ ] `create_merged_candidate` 只能新建，来源含混合候选时拒绝并返回稳定错误码
- [ ] `create_merged_candidate` 记全部来源作者，来源作者调该混合候选的任何工具均被拒绝
- [ ] 两个新工具走接口层留痕，写调用 fail-closed；账本不含报告正文与候选内容
- [ ] `_CAPABILITY_ORDER` 扩展为七档，未知能力名仍在启动时被拒绝
- [ ] 现有两领域全量测试通过（收紧是纯减法，不应打破任何已有用例）
- [ ] 回写验证命令、结果与提交号到本票 Notes

## Notes

**2026-10-24T15:20:00Z**

来源：`ai4-t2wc` 收口，assignee 由 Frank Qi 定为 hanjiang。依据 Gitee issue IKQ6XQ 的阻塞清单：`ai4-w73z`、`ai4-he04`、`ai4-5z9e`、`ai4-oebi`、`ai4-8dgd` 五张票全部等这一项落地。

与本票并行的其他票：

- 「中央 Agent 能力接口收口」(ai4-rlv6)：本票完成后，其工具清单里 `append_mapping_prereview_log` 等四个分领域名字需改为单数名 + 领域参数。
- `ai4-w73z` 已勾选的「中央 Agent 五类能力边界均有服务端鉴权与测试」在收紧后不再准确，需 hanjiang 在该票内修正描述。

范围界定：只动 `sci-weave/centre-control/research-map` 与 `sci-weave/centre-control/research-wiki` 两个子项目。不动 Registry（`kind` 已实现）、不动 Centre Agent 进程骨架、不动邮件通知。
