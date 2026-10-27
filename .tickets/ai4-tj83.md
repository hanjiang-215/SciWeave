---
id: ai4-tj83
status: open
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

- [ ] `libs/mcp-libs/research-mapping/mcp.json` 只保留 `get_formal_mapping` / `get_formal_mapping_at_revision` / `list_candidates`，其余工具从卡片移除。
- [ ] `libs/mcp-libs/research-wiki/mcp.json` 只保留 `get_formal_wiki` / `list_wiki_candidates`，其余移除（`list_reviewable_wiki_candidates` 一并移出，与 mapping 侧对称）。
- [ ] 移除前逐个核对 `management.py` 的 `TOOL_CAPABILITIES`，确认保留的都是真读、移除的都涉及写正式域或写治理日志；核对结果已写进第三节的对照表，落地时复核一遍即可。
- [ ] `draft-buffer` / `email-service` / `sciencepal` 三张卡不动（并说明为什么不动）。
- [ ] 卡片里保留的工具，其 `input` / `output` / `description` 与服务端 `TOOL_DEFINITIONS` 逐字一致（这也是移除动作的必要前置：改卡片前先确认现状）。
- [ ] 补测试：`load_mcp_registry("libs/mcp-libs/")` 加载后，`research-mapping` 与 `research-wiki` 的工具集合恰好等于白名单，多一个少一个都失败。
- [ ] `libs/local-mcp-libs/local-literature.yaml` 的去留明确处理，并在票里说明理由。
- [ ] 既有依赖这些卡片工具面的测试与文档同步更新（`ai4-emfn` / `ai4-b4zb` 的成果不能被本票改坏）。
- [ ] runtime 全量测试通过；`compileall` 与 `git diff --check` 通过。

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
