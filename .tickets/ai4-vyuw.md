---
id: ai4-vyuw
status: open
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

- [ ] 在当前 HEAD 上重跑 `run_iris_mapping_pipeline.py`，退出码 0，六步 MCP 时序完整。
- [ ] 三条失败路径均返回预期错误码：`forbidden`、`stale_base`、驳回后正式图不含被驳回节点。
- [ ] `iris_platform_pipeline.json` 重生成且为 UTF-8，`python3 -m json.tool` 可解析。
- [ ] `demo-script.md` 第 5 段与计时表的「实际」列回填真实数字，总时长复核到 5 分钟以内。
- [ ] 明确写出演示是否包含 Web 看板，并据此更新 `demo-script.md` 的窗口准备段。
- [ ] 写明 SciencePal 段不需要公网 MCP 端点，`deploy-central-mcp.md` 的隧道方案仅作可选路径保留。
- [ ] 运行前置（TerminusDB 已启动、凭据经环境变量）在 `evidence-card.md` 中复核一遍，确认与新证据一致。

## Notes

**2026-10-27 登记（Frank Qi）**

身份核对：本票 assignee 为 Frank Qi，当前分支 `feature/frank-qi`、`git config user.name=Frank Qi`，一致。

依赖 `ai4-483l` / `ai4-j7g2` 的理由：第 2、3 段的两次运行会一并产出计时数字，脚本修好后再跑一遍才是不返工的计时。若时间紧张，可先只跑第 5 段并单独回填，届时解除依赖。

本票不含「SciencePal 实际承载执行」这一赛事硬门槛，那仍是 `ai4-aaff` 的未勾选项。
