---
id: ai4-tj83
status: closed
deps: []
links: [ai4-cxnm, ai4-4r0h]
created: 2026-10-27T10:19:35Z
type: task
priority: 2
assignee: Frank Qi
tags: [toolkit, mcp, permission, task-agent]
---
# 套件出厂 MCP 卡改为 task-agent 视角并划分工具权限

`libs/mcp-libs/` 是套件的**出厂默认配置**，不是领域服务的完整目录。但现在的卡片是照着领域服务端全量抄的，把「只有研究员本人在自己的 MCP 上才该做」的写工具也列了进去，而 runtime 不做任何工具级过滤。

## 一、卡片列着写正式域的工具，但没有任何过滤

`research-mapping` 卡 11 个工具里，`submit_candidate` / `preview_candidate` / `record_review` / `formalize_candidate` / `reconcile_formalization` / `append_prereview_log` / `create_merged_candidate` 都是写正式域的；`research-wiki` 同样带 `submit_wiki_candidate` / `create_wiki_merge_request` / `decide_wiki_review` / `formalize_wiki` / `reconcile_wiki_formalization`。

卡片每个工具有 `allowed:` 字段（`_tool()` 从 `data["allowed"]` 或 `data["access"]` 读，`mcp_resources.py:31`），但 `catalog()` 只是把它原样透出：

```
runtime/src/work_agent_runtime/mcp_resources.py:29
    "allowed": list(tool.allowed),
```

全树 grep `.allowed` / `allowed=` 的结果只有 `config.py:98`（校验 `allowed_mcp_resources` 的**服务器名**）和上面这处透出。**没有任何代码用工具级 `allowed` 做过滤**，`config.py` 只校验服务器名不校验工具名。

所以一张卡挂上去，那台 MCP 的**全部**工具 agent 都能调。而 `ai4-x0ay` 要给 `mapping-reader` / `wiki-reader` 挂地图与 wiki 卡——按现在的卡片，这两个只读 agent 会拿到正式的写能力。

## 二、采用的办法：卡片只列 task-agent 允许用的工具

`libs/mcp-libs/` 改成「task-agent 视角的能力面」，而不是领域服务的完整目录：

| 卡片 | 现状 | 改成 |
| --- | --- | --- |
| `research-mapping` | 11 工具（含 7 个写正式域） | 只读：`get_formal_mapping` / `get_formal_mapping_at_revision` / `list_candidates` |
| `research-wiki` | 11 工具（含 6 个写正式域） | 只读：`get_formal_wiki` / `list_wiki_candidates` |
| `draft-buffer` | 7 工具 | 保留全部：草稿箱本来就是 Task Agent 的写入目标 |
| `email-service` | 2 工具 | 保留全部 |
| `sciencepal` | 5 工具 | 保留全部 |

理由：套件里放一份「task-agent 视角的能力面」最诚实，也和 `config.py` 现有的「只认服务器名」校验一致，零新增机制。

**两边必须对称。** 上一版给 wiki 多留了一个 `list_reviewable_wiki_candidates`，却把 mapping 对应的 `list_reviewable_candidates` 删了——同一类工具在两个领域一个留一个删，研究员换领域就要重新学一遍权限。两个 `list_reviewable_*` 都是候选**预审**用的（`_READ_CAPABILITIES`，供 Centre Agent 拉「可审的候选」），不属于研究员侧 Task Agent，**两边都移出**。

> 命名与工具面不对称本身（`preview_wiki_review` vs `preview_candidate`）已另提 Gitee issue（IKQZ02）请中央侧核对；本票不等它，按上表执行。

不选「卡片保留全量、在生成 `fast-agent.yaml` 时按 `allowed:` 过滤」：fast-agent 的 `tools` 确实是 `dict[server, list[tool]]`，技术上可行，但那是给「研究员自己装了别的服务器」的场景准备的，出厂默认不该走这条路，而且需要新增一层映射与测试。

不选「靠 agent 的 instruction 约束」：`ai4-z3z4` 明说处置面工具签名两边要一致，把边界交给提示词等于没有边界。

## 三、读工具的名字要核对真实服务端

`research-wiki` 卡里有一个 `preview_wiki_review`，而 `research-mapping` 对应的是 `preview_candidate`。这两处命名不对称，改卡片前要对着 `management.py` 的 `TOOL_CAPABILITIES` 逐条确认哪些是真读、哪些写审计日志。

已核对（两边都是 11 个工具，`_TOOL_CAPABILITIES` 逐条对齐）：

| 能力集合 | mapping | wiki | Task Agent 要不要 |
| --- | --- | --- | --- |
| `_READ_CAPABILITIES`（`read` / `centre`） | `get_formal_mapping`、`get_formal_mapping_at_revision`、`list_candidates`、`list_reviewable_candidates` | `get_formal_wiki`、`list_wiki_candidates`、`list_reviewable_wiki_candidates` | 前三/前二 **要**；`list_reviewable_*` **不要**（预审用） |
| `_CANDIDATE_SUBMIT_CAPABILITIES` | `submit_candidate` | `submit_wiki_candidate` | 不要 |
| `_CANDIDATE_REVIEW_CAPABILITIES` | `preview_candidate`、`record_review` | `preview_wiki_review`、`create_wiki_merge_request` | 不要 |
| `_FORMALIZE_CAPABILITIES` | `formalize_candidate`、`reconcile_formalization` | `decide_wiki_review`、`formalize_wiki`、`reconcile_wiki_formalization` | 不要 |
| `_PREREVIEW_LOG_CAPABILITIES` | `append_prereview_log` | `append_prereview_log` | 不要 |
| `_MERGED_CANDIDATE_CAPABILITIES` | `create_merged_candidate` | `create_merged_candidate` | 不要 |

`append_prereview_log` 看着像「写日志」，实际是**预览规则链**的一部分（`ai4-b4zb` / `333cd12` 把它定义成四列键的 upsert）。它属于中央预审，不属于研究员侧 Task Agent，本票一并移出只读卡。

`preview_*` 两处都在 `_CANDIDATE_REVIEW_CAPABILITIES` 里，本来就该移出；命名不对称与本次移除无关，留作中央侧的一致性问题。

## 四、顺带处理占位卡

`libs/local-mcp-libs/local-literature.yaml` 只有一个 `search` 工具的占位卡，背后没有服务实现。`ai4-cxnm` 会交付真实的 `literature-search` 卡（放 `libs/mcp-libs/`）。本票决定这张占位卡的去留：建议删除，避免研究员以为它是可用的。

## Acceptance Criteria

- [x] `libs/mcp-libs/research-mapping/mcp.json` 只保留 `get_formal_mapping` / `get_formal_mapping_at_revision` / `list_candidates`，其余工具从卡片移除。
- [x] `libs/mcp-libs/research-wiki/mcp.json` 只保留 `get_formal_wiki` / `list_wiki_candidates`，其余移除（`list_reviewable_wiki_candidates` 一并移出，与 mapping 侧对称）。
- [x] 移除前逐个核对 `management.py` 的 `TOOL_CAPABILITIES`，确认保留的都是真读、移除的都涉及写正式域或写治理日志；核对结果见第三节对照表，落地复核结论见备注（`list_reviewable_*` 是唯一两个只读却被移出的，理由已写进测试）。
- [x] `draft-buffer` / `email-service` / `sciencepal` 三张卡不动（并说明为什么不动）。
- [x] 卡片里保留的工具，其 `input` / `output` / `description` 与服务端 `TOOL_DEFINITIONS` 逐字一致（这也是移除动作的必要前置：改卡片前先确认现状）。
- [x] 补测试：`load_mcp_registry("libs/mcp-libs/")` 加载后，`research-mapping` 与 `research-wiki` 的工具集合恰好等于白名单，多一个少一个都失败。
- [x] `libs/local-mcp-libs/local-literature.yaml` 的去留明确处理，并在票里说明理由。
- [x] 既有依赖这些卡片工具面的测试与文档同步更新（`ai4-emfn` / `ai4-b4zb` 的成果不能被本票改坏）。
- [x] runtime 全量测试通过；`compileall` 与 `git diff --check` 通过。

## Not in Scope

- 不实现工具级白名单过滤机制（`allowed:` 字段保持为描述字段，不做运行时强制）。
- 不交付 `literature-search` 服务与卡片本身（`ai4-cxnm`）。
- 不改领域服务端 `management.py` 的工具定义——本票只改套件侧的卡片。
- 不决定文献 agent 怎么用这些卡（`ai4-x0ay`）。
- 不动 `custom-mcp/sciencepal-bridge`。

## Notes

**2026-10-27 立项（Frank Qi）**

> *This was generated by AI during triage.*

身份核对：assignee `Frank Qi`、分支 `feature/frank-qi`、`git config user.name=Frank Qi`，三者一致。

立项依据是 2026-10-27 设计轮次的 Q21（「map / wiki 卡里的写正式域工具，要不要对 task-agent 关掉」，选定「卡片只列允许的工具」）。「卡片列全量、runtime 不过滤」这个事实是用 `grep -rn '\.allowed\|allowed='` 在 `runtime/src` 与 `service-template` 全树核实的，只命中透出与服务器名校验两处。

与 `ai4-emfn` / `ai4-b4zb` / `ai4-ced7` 不重复：那三张处理的是「卡片与服务端工具面**漂移**」（数量对不上、描述不一致）；本票处理的是「对上了，但**不该给**」。前者是同步问题，后者是权限边界问题。

与 `ai4-x0ay` 互为前置：本票不先做完，`mapping-reader` / `wiki-reader` 就会拿到写正式域的能力。

**2026-10-27 复核修订（Frank Qi）**

> *This was generated by AI during triage.*

8. **只读工具面两侧不对称。** 上一版给 wiki 留了 `list_reviewable_wiki_candidates`，mapping 侧的 `list_reviewable_candidates` 却删了。两个都属 `_READ_CAPABILITIES` 且都是候选预审用途，同属研究员侧 Task Agent 不该有的能力，现改为两边都移出。第二节的表、第三节的对照表与 AC 同步更新。
9. **第三节补了逐条能力核对表。** 原文只说「改卡片前要对着 `management.py` 的 `TOOL_DEFINITIONS` 逐条确认」，没给结论；现按两个服务的 `_TOOL_CAPABILITIES` 全量比对后列成表，落地时只需复核不需重新调研。`preview_*` 两处都在 `_CANDIDATE_REVIEW_CAPABILITIES`，命名不对称与本次移除决定无关。

**2026-10-27 完成（Frank Qi）**

> *This was generated by AI during triage.*

提交 `b0b34cc`。

落地结论：

- `research-mapping` 卡只剩 `get_formal_mapping` / `get_formal_mapping_at_revision` / `list_candidates`；`research-wiki` 只剩 `get_formal_wiki` / `list_wiki_candidates`。
- `draft-buffer`（7）、`email-service`（2）、`sciencepal`（5）不动。理由不是「先不动」：草稿箱是 Task Agent 唯一合法的写入目标（提交候选前必须先有草稿），邮件通知是它的对外出口，SciencePal 是它委派执行的通道——三张卡的工具全是 Task Agent 自己就该用的。另外 `sciencepal` 卡只有 5 个工具，而服务端 `main.py` 有 6 个（多了 `sciencepal_report`）；那个工具写中央草稿箱、属于 `ai4-roow` 的范围，本票按「不动」处理，不顺手加也不顺手删。
- `libs/local-mcp-libs/local-literature.yaml` **删除**。它只有一个 `search` 工具、背后没有任何服务实现，`project_dir_env` 指向的目录也不存在；真实的文献检索已由 `ai4-cxnm` 的 `libs/mcp-libs/literature-search/` 交付。留着它只会让研究员以为能用。目录保留 README 并写明「出厂不预置卡片」，另有测试钉住「空本地目录不算错误」（这正是 `ai4-4r0h` 修过的那个坑）。

落地时复核出两处票内没写到的事实，一并处理了：

1. **`input` 不是「逐字一致」，是全都缺一个键。** 11 个 mapping 工具与 11 个 wiki 工具的卡片 `input` 都没有 `"additionalProperties": false`，而服务端 `inputSchema` 全都有。AC 第 5 条要求逐字一致，所以不是「复核通过」而是「复核不通过」，保留的 5 个工具已按服务端原文重写。`append_prereview_log` 的 `description` 也有出入（该工具本票已移出，未修）。
2. **`output` 是编的。** 原卡片里 `get_formal_mapping_at_revision` 的 `output` 只有 `{"status": "string"}`，而它和 `get_formal_mapping` 共用 `_formal_query_result()`，实际返回 10 个字段（含 `published_by`，`ai4-2raq` 的成果）。5 个保留工具的 `output` 已按 `_formal_query_result` / `_list_candidates` / `_formal_wiki_result` / `_list_wiki_candidates` 的真实投影重写。

`list_reviewable_*` 的处理：两张卡都移出。它们是 `_READ_CAPABILITIES`（只读），但服务的是候选**预审**队列，属于中央侧而非研究员侧 Task Agent。这一条不能用「移出的都涉及写」来证明，所以测试把它单列为 `PRE_REVIEW_EXCEPTIONS`，并额外断言两个领域各有一个、都不在保留集里——避免再次出现「一边留一边删」。

新增 `runtime/tests/test_domain_card_permissions.py`（15 条），用 `ast` 从 `management.py` 读 `TOOL_DEFINITIONS` 与 `_TOOL_CAPABILITIES`（直接 import 需要 `audit_trail` 在路径上，卡片测试不该依赖中央 workspace 装好）。它钉住：白名单精确相等、没有 Owner 侧工具泄漏、**白名单与移出集合覆盖服务端全部工具**（服务端新增工具时既不会被静默继承也不会被静默丢掉）、保留工具的 `description` / `input` 与 `additionalProperties` 逐字一致、`output` 与 `published_by` 存在。

同步更新：

- `runtime/tests/test_standard_mcp_cards.py` 的 `EXPECTED` 改成新的工具集，并在注释里说明「这是能力面不是镜像」，避免下一个人照着服务端把它补回去。
- `deploy-task-agent-skills/configure-mcp/references/mcp-resources.md` 原文写「三张卡片的工具清单与领域管理 MCP 的真实工具面一一对应」——这句话现在是错的，已重写成六张卡的对照表，并写明 runtime 不做工具级过滤、因此卡片必须按能力面裁剪。

验证：runtime **168 passed**（原 153）；`compileall` 通过；`git diff --check` 干净。

给 `ai4-x0ay` 的前提：`mapping-reader` 现在只能读正式图、正式 wiki 与候选提交记录，即使它挂上了这两张卡也拿不到写能力。
