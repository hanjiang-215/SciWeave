# MCP 资源参考

标准资源共六张卡，都在 `libs/mcp-libs/`：

| 卡片 | 传输 | 这份出厂配置给 Task Agent 的工具 |
| --- | --- | --- |
| `research-mapping` | Streamable HTTP | `get_formal_mapping`、`get_formal_mapping_at_revision`、`list_candidates` |
| `research-wiki` | Streamable HTTP | `get_formal_wiki`、`list_wiki_candidates` |
| `draft-buffer` | Streamable HTTP | 全部 7 个：草稿箱本来就是 Task Agent 的写入目标 |
| `email-service` | Streamable HTTP | 全部 2 个 |
| `sciencepal` | stdio | 全部 5 个 |
| `literature-search` | stdio | 全部 2 个：`search`、`get_abstract` |

**`libs/mcp-libs/` 是「Task Agent 视角的能力面」，不是领域服务的完整目录。** 领域管理 MCP 的 `submit_candidate` / `preview_candidate` / `record_review` / `formalize_candidate` / `reconcile_formalization` / `append_prereview_log` / `create_merged_candidate`，以及 Wiki 侧对应的一整套，都要求 `candidate_submit` / `candidate_review` / `formalize` / `prereview_log` / `merged_candidate` 这些 Owner 侧能力，不属于研究员自己的 Work Agent，因此不在这两张卡里。

`list_reviewable_*` 只要求 `read` / `centre`，但它是候选**预审**队列，属于中央侧；两个领域一起移出，保持对称——一个领域保留、另一个删掉，研究员换领域就要重学权限。

runtime **不做工具级过滤**：`config.py` 只校验 `allowed_mcp_resources` 里的服务器名，卡片的 `allowed:` 是描述字段。所以「卡片列了什么，agent 就能调什么」——这正是卡片要按能力面裁剪、而不是照抄服务端目录的原因。服务端的能力档位（read / centre / candidate_submit / candidate_review / formalize / prereview_log / merged_candidate）仍然会独立拒绝越权调用，卡片只是不主动提供。

新增一张卡或给现有卡加工具前，先问一句「研究员的 Task Agent 是否真该有这个能力」；写正式域的一律不进 `libs/mcp-libs/`。

`LOCAL_MCP_LIBS` 可指向本地描述符目录；兼容的 1.x 本地同名资源覆盖标准资源，同名冲突或不兼容版本应失败。本地目录出厂只有 README（没有卡片），`load_mcp_registry` 对空目录返回「无本地覆盖」而不报错。资源库只提供目录和配置约定，不主动建立网络连接；地址和令牌通过资源描述符声明的环境变量提供，真实值不提交。
