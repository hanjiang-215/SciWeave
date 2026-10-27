---
id: ai4-vyuw
status: closed
deps: [ai4-483l, ai4-j7g2]
links: [ai4-aaff, ai4-v869]
created: 2026-10-27T01:01:48Z
type: task
priority: 0
assignee: Frank Qi
parent: ai4-aaff
tags: [demo, evidence, mapping, rehearsal]
---
# develop 合并后复跑 Iris 治理链路，回填计时与演示载体

`humans/competition/demo-evidence/iris_platform_pipeline.json` 是 2026-10-24 在 `feature/hanjiang` 上产出的一次运行记录。此后 `develop` 已合入 `feature/frank-qi`（合并提交 `e54aa92`，69 个提交、181 个文件），演示第 5 段依赖的 `research-map` 管理 MCP 与治理服务都在改动范围内。**现有证据不能证明当前 HEAD 上链路仍然成立。**

静态核对结论（2026-10-27）：代码层面未发现断裂，但需要一次真实运行来确认。

- 演示脚本调用的 8 个 MCP 工具的必填参数与合并后 `management.py` 的 `inputSchema` 完全一致：`get_formal_mapping{mapping_domain_id}`、`submit_candidate{change_set, idempotency_key}`、`preview_candidate{proposal_id, base_formal_revision_id, candidate_head}`、`record_review{buffer_id, decision, reason}`、`formalize_candidate{merge_request_id, operation_id}`、`list_candidates{submission_id}`。
- `MappingManagementService` / `MappingReviewService` / `MappingFormalizationService` / `create_management_mcp_server` 的构造签名未被合并改动。
- 演示脚本用到的 `SqliteStore` 方法 `initialize` / `add_formal_revision` / `add_formalization_result` / `set_current_formal_revision` / `count_candidate_records` 全部存在。

未验证项即本票范围：真实执行结果、计时、以及证据文件重生成。

## Design

1. 在 `feature/frank-qi` 当前 HEAD 上按 `evidence-card.md` 第 85 行起的命令重跑 `run_iris_mapping_pipeline.py`（本机 TerminusDB，凭据走环境变量），要求退出码 0、六步时序全部出现、三条失败路径均返回预期错误码。
2. 重生成 `iris_platform_pipeline.json`，编码按 `ai4-fe3w` 转 UTF-8。
3. 记录实际耗时，回填 `demo-script.md` 第 5 段的「实际」列，并核对总时长。当前表内合计为 310s（≈5:10，已超 5 分钟上限，靠压缩段 3 讲解回收），实测数字出来后重算一次。
4. 明确演示载体：`demo-script.md` 第 10 行要求准备「Web 看板或任务面板、SciencePal、TerminusDB 或审计视图」三个窗口。看板默认走 fixture（`web-ui/src/App.vue:15`），会显示「演示数据模式 / 不代表真实服务状态」横幅，且 `dashboard-api` 的 `queue` 来源无实现。**建议本票直接决定不演示看板**，第 6 段改用 TerminusDB 界面或审计账本，把该决定写回 `demo-script.md`，避免演示当天临时接入。
5. SciencePal 段（第 2、3 段）不在本票：`check_iris_input.py` / `run_iris_baseline.py` 都是纯标准库、不调 MCP，因此**不需要为演示开放公网 MCP 端点**；`deploy-central-mcp.md` 的隧道方案只在走路径 B（skill 内调 MCP）时才需要。该结论写入演示前置说明，可省掉一个当天会挂的环节。

## Acceptance Criteria

- [x] 在当前 HEAD 上重跑 `run_iris_mapping_pipeline.py`，退出码 0，六步 MCP 时序完整。
- [x] 三条失败路径均返回预期错误码：`rejected`（驳回后正式图不含被驳回节点）、`forbidden`，第三条为 `base_revision_missing` 而非本票原写的 `stale_base`（见 Notes 的口径修正）。
- [x] `iris_platform_pipeline.json` 重生成且为 UTF-8，`python3 -m json.tool` 可解析。
- [x] `demo-script.md` 第 5 段与计时表的「实际」列回填真实数字，总时长复核到 5 分钟以内。
- [x] 明确写出演示是否包含 Web 看板，并据此更新 `demo-script.md` 的窗口准备段。
- [x] 写明 SciencePal 段不需要公网 MCP 端点，`deploy-central-mcp.md` 的隧道方案仅作可选路径保留。
- [x] 运行前置（TerminusDB 已启动、凭据经环境变量）在 `evidence-card.md` 中复核一遍，确认与新证据一致。

## Notes

**2026-10-27 登记（Frank Qi）**

身份核对：本票 assignee 为 Frank Qi，当前分支 `feature/frank-qi`、`git config user.name=Frank Qi`，一致。

依赖 `ai4-483l` / `ai4-j7g2` 的理由：第 2、3 段的两次运行会一并产出计时数字，脚本修好后再跑一遍才是不返工的计时。若时间紧张，可先只跑第 5 段并单独回填，届时解除依赖。

本票不含「SciencePal 实际承载执行」这一赛事硬门槛，那仍是 `ai4-aaff` 的未勾选项。

**2026-10-27 实现与验证（Frank Qi）**

提交：`0d829ad`（复跑 + 计时回填 + 载体决策）、`e7a001f`（证据转 UTF-8）、`991edb9`（计时压到 260s）、`f556dba`（文档对齐）。

复跑结果（本机 TerminusDB `127.0.0.1:6363`，凭据经环境变量）：

```text
$ python3 humans/competition/demo-evidence/run_iris_mapping_pipeline.py
exit=0  耗时 1.1s
result.status: completed        formal_mapping_contains_t4: true
failure_paths: reviewer_without_submit=forbidden
               stale_base_candidate={"status":"rejected","reason_code":"base_revision_missing",...}
               rejected_review=rejected
events: 14
```

`develop` 合入未破坏第 5 段，与登记时的静态核对结论一致。

**口径修正（重要，评审发现）**：本票原写「过期基准返回 `stale_base`」，实际返回 `base_revision_missing`。原因是 `ai4-eex0` 早已把基准校验前移到写入时门禁——不存在的基准在提交即被拒绝，根本进不到预审，「基准存在但已非当前」才是 `stale_base` 的适用范围。这是票据措辞过期，不是代码回归。已在验收项与 `demo-script.md`、`evidence-card.md` 中改正为 `base_revision_missing`。

**演示载体决策：不演示 Web 看板。** 看板在 `apiUrl` 为空时走 fixture（`web-ui/src/App.vue:15`），页面渲染「演示数据模式 / 不代表真实服务状态」橙色横幅；且 `dashboard-api` 的 `queue` 来源无实现。第 6 段改用 TerminusDB 界面或接口层审计账本，都是真实数据，零实现成本。窗口从 3 个减到 2 个（SciencePal + 终端），段 6 并入段 5 尾部，切屏次数从 3 次降到 1 次。

**公网端点结论**：演示第 2–4 段只跑两个纯标准库脚本，不调中央 MCP，path A / path B 都不走，`deploy-central-mcp.md` 的隧道方案可整段跳过。初稿写成「仅路径 B 需要」是超出依据的表述（`sciencpal-onboarding/README.md:12` 明确说路径 A/B 都依赖出站），已在 `f556dba` 改为区分「本场演示」与「后续 v869 对接」，既不与预案矛盾，也划清演示范围。

**计时**：三个脚本实测 0.02s / 0.02s / 1.1s，说明超支全部来自讲解。初版 310s 超上限 10s，压缩段 1（40→25s）、段 3（60→45s）、段 6 并入段 5，并给段 5 加时（90→100s），合计 260s（≈4:20），留 40s 缓冲。段 2、段 4、段 5 不砍。

**遗留**：口播节奏是估算，需录制时掐表回填；SciencePal 实演记录仍待回填（属 `ai4-aaff` 硬门槛，不在本票）。
