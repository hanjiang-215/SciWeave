---
id: ai4-t2wc
status: closed
deps: [ai4-oz3s]
links: [ai4-ujvn, ai4-oz3s, ai4-rlv6]
created: 2026-10-21T15:37:31Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-fv1r
tags: [centre-agents, registery, permission, wayfinder:grilling]
---
# 注册表登记中央 Agent 与其开放面

在注册表加 `kind` 区分端侧与中央，并为中央 Agent 定义开放面：读两套管理 MCP 的候选与正式版本，写预审日志，新建混合候选分支，其余全禁。

## Question

中央 Agent 是否进注册表、登记什么字段、它的开放面包含哪些工具。

## Design

### 进注册表，加 kind

中央 Agent 要进注册表。它与端侧 Agent 同表，用 `kind` 区分：

| `kind` | 谁 | 所属主体 | 部署位置 |
| --- | --- | --- | --- |
| `endpoint` | 研究员自持的 task-agent | 必填，`principal_id` | 部署者自行描述 |
| `centre` | 中央 Agent | 留空 | 中央服务器，不需要描述 |

不新增规则集版本等字段：那是预审报告里的内容，不是注册事实。注册表仍然只回答「谁在跑什么」，不因为多了中央这一类就变成配置源或授权表。

### 中央 Agent 的开放面

在「端侧 Agent 的注册记录与中央服务开放面」(ai4-ujvn) 已定的端侧开放面之外，中央 Agent 另有一组能力名。此处的「档」按能力名计，不按主体计：能力名之间平铺，互不包含。

**允许的工具（白名单，共 8 个）**

| 领域 | 工具 | 能力名 |
| --- | --- | --- |
| Mapping | `get_formal_mapping` | `centre` |
| Mapping | `list_candidates` | `centre` |
| Mapping | `list_reviewable_candidates` | `centre` |
| Wiki | `get_formal_wiki` | `centre` |
| Wiki | `list_wiki_candidates` | `centre` |
| Wiki | `list_reviewable_wiki_candidates` | `centre` |
| Mapping / Wiki | `append_prereview_log`（必需领域参数） | `prereview_log` |
| Mapping / Wiki | `create_merged_candidate`（必需领域参数） | `merged_candidate` |

**禁止的工具（两套管理 MCP 各 5 个与 6 个，全部不授予中央 Agent）**

- Mapping：`submit_candidate`、`preview_candidate`、`record_review`、`formalize_candidate`、`reconcile_formalization`
- Wiki：`submit_wiki_candidate`、`preview_wiki_review`、`create_wiki_merge_request`、`decide_wiki_review`、`formalize_wiki`、`reconcile_wiki_formalization`

要点：

- **读的范围比端侧宽**：端侧只看得到自己提交的草稿，中央 Agent 要看到全部候选才能判冲突。这是它存在的理由，不是越权。
- **两个写工具分开授权**：`prereview_log` 与 `merged_candidate` 是两个独立能力名，凭据可以共用，工具面必须分开。见「预审报告的追加日志契约」(ai4-oz3s)。合成一个工具等于让「能写报告」的凭据顺带获得「能改候选内容」的能力。
- **不写草稿箱**：草稿的一审是人，中央 Agent 的工作从候选存在开始。`submit_candidate` 与 `submit_wiki_candidate` 一并禁止，理由同此：中央 Agent 不自己造候选。
- **不参与正式化**：`formalize_*`、`reconcile_*`、`decide_wiki_review`、`record_review` 全部禁止。审批与正式版本推进是 Project Owner 的职责。

### 仍然不是权限系统

登记表本身不参与鉴权这一条不变。中央 Agent 的能力由它的工具面决定，登记只留痕。中央 Agent 跑在中央自己的服务器上，平台对它是有强制力的，所以它的收口可以做得比端侧硬——但那是工具面的事，不是登记表的事。

### Project Owner 联系方式

已移出本票。Project Owner 的联系人登记字段、`contact_email` 的用途边界与查询错误码，由「Registry 登记事实与中央服务开放面规格」(ai4-ujvn) 定义，实现见「实现 Registry 登记与查询 MCP」(ai4-w4su) 的 `get_principal_contact`。原文保留在 Notes 备查。

## Acceptance Criteria

- [x] 注册表增加 `kind` 字段，取值 `endpoint` 与 `centre`，中央类目所属主体留空
- [x] 不为中央 Agent 增加规则集版本等运行时字段
- [x] 开放面增加中央 Agent 的工具白名单，读写范围明确到工具粒度
- [x] 明确中央 Agent 读全部候选，不受「只看自己提交」限制
- [x] 明确中央 Agent 不写正式版本、不改已有候选、不写草稿箱接纳状态
- [x] 明确两个写工具分开授权，凭据可共用但工具面不合并
- [x] 登记仍然不参与鉴权

## Notes

**2026-10-21T23:40:00Z**

来源：2026-10-21 第五轮讨论。用户裁决中央 Agent 要进注册表；由本票确定字段形态。

对「端侧 Agent 的注册记录与中央服务开放面」(ai4-ujvn) 的影响：该票的三档开放面需要增加第四档，登记字段需要增加 `kind`。由该票负责人裁决是否接受，本票不直接改其正文。

**2026-10-24T15:20:00Z**

收口（2026-10-24，assignee 本人操作）。此前四轮讨论的结论落地为本票正文，变更如下：

- **标题与措辞**：标题由「注册表登记中央 Agent 与开放面第四档」改为「注册表登记中央 Agent 与其开放面」。上一则 Notes 里的「三档」「第四档」是按主体分档时的旧说法，已作废；本票的开放面按能力名计，能力名平铺、互不包含。原文保留。
- **开放面改为工具白名单**：正文原表只有一行「能做什么 / 不能做什么」，实现者无法判断 `preview_candidate`、`record_review` 是否属于「读」。现改为明确白名单：保留 6 个读工具（两领域各 3 个，能力名 `centre`），新增 2 个写工具（`append_prereview_log` / `create_merged_candidate`，各带必需领域参数，能力名分别为 `prereview_log` / `merged_candidate`），并把两领域共 11 个工具明确列为禁止。
- **写工具命名**：「中央 Agent 能力接口收口」(ai4-rlv6) 与 `centre-agents/README.md` 此前写的分领域四名单数名（`append_mapping_prereview_log` 等），本票改为单数名 + 领域参数，与该票读工具的写法一致；`rlv6` 的对应措辞需同步。
- **Project Owner 联系方式移出**：该节与 `ai4-ujvn` 的 Resolution、`ai4-w4su` 的 `get_principal_contact` 实现重叠，正文改为指向这两张票。原文保留如下：

  > Project Owner 的登记记录可以包含用于通知的 `contact_email`，或等价的通知联系人记录。该字段只用于定位通知收件人：不保存邮箱密码、SMTP 令牌、API Key 或其他凭据；不参与鉴权、权限判断或正式化决定；邮箱变更属于登记事实变更，应保留可追溯记录；中央 Agent 只能据此创建 PO 通知请求，不能把邮件回复当作批准；实际邮件投递由独立通知组件完成。

- **kind 三条验收的证据**（原 AC 已实现但未勾选）：
  - `kind` 取值校验：`sci-weave/centre-control/registry/src/registry/service.py:117-130`。`endpoint` 要求非空 `principal_id`，`centre` 要求留空，非法值返回 `invalid_agent_kind`。
  - 研究员不能登记 `centre` Agent：`sci-weave/centre-control/registry/tests/test_http.py:209-221`，返回 `denied`。
  - 登记不参与鉴权：Registry 的能力判断只看调用方 `caller_type` 与 `service_role`，不读 `workflow_agent` 表的 `kind`。
- **实现范围不在本票**：本票只定规格。摘除 11 个工具的 `centre` 授权、新增 2 个写工具与 2 个能力名，由「收紧管理 MCP 的中央 Agent 开放面并补两个预审写工具」承载（assignee hanjiang）。
- **对 w73z 的影响**：该票已勾选「中央 Agent 五类能力边界均有服务端鉴权与测试」。收紧后中央 Agent 不再覆盖正式化工具，该项描述需要 hanjiang 在自己票里修正。已通过 Gitee issue IKQ6XQ 知会。
