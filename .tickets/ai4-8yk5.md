---
id: ai4-8yk5
status: closed
deps: []
links: [ai4-he04, ai4-oz3s, ai4-8dgd, ai4-rlv6]
created: 2026-10-28T00:23:47Z
type: bug
priority: 1
assignee: Frank Qi
tags: [mapping, gateway, correctness]
---
# Mapping 管理 MCP 缺 create_merge_request：preview 之后没有下一步

Mapping 侧的审核链在 MCP 上断成两截。

PO 的动作序列是 `preview_candidate` → 拿到 `preview_id` → `record_review(buffer_id, ...)` →
`formalize_candidate(merge_request_id=buffer_id, ...)`。中间那个 `buffer_id` 由
`ReviewService.create_buffer(preview_id)` 产生，但**没有任何 MCP 工具能调用它**：
全仓库只有 `tests/` 与 `humans/competition/demo-evidence/run_iris_mapping_pipeline.py:390`
直接调了 `create_buffer`。Wiki 侧一直有 `create_wiki_merge_request`，Mapping 侧没有。

后果：一个持有 `candidate_review` 的 Project Owner 能预览候选，然后无处送决定。
`record_review` 和 `formalize_candidate` 都要求 `buffer_id`，而 `preview_id` 不被任何
buffer 工具接受（`buffer_id = "buffer-" + sha256_json({"preview_id": ...})`）。
审核链在 MCP 层面不可完成，只有直接写 Python 才走得通。

## Acceptance Criteria

- [x] `create_merge_request(preview_id)` 作为 MCP 工具存在，返回 `buffer_id` 等字段
- [x] 能力归 `candidate_review`（与 `record_review` 同级），不是 `formalize`
- [x] `buffer_id` 由 `preview_id` 派生，重复调用幂等
- [x] `major` 写入工具清单同步（`_WRITE_TOOLS`、`_TOOL_CAPABILITIES`、`_target_type`、`_target_id`、`TOOL_DEFINITIONS`）
- [x] 测试覆盖：正常路径、幂等重放、未预览过的 `preview_id`

## Notes

**2026-10-28T00:30:00Z**

已实现，见 `sci-weave/centre-control/research-map/src/research_mapping/management.py` 的
`_create_merge_request`：handler 注册在 `_record_review` 之前（同一能力档，
注册顺序不影响路由，但读起来顺着审核链），调用 `self._review_service.create_buffer(preview_id)`，
返回 `{buffer_id, preview_id, proposal_id, base_formal_revision_id, candidate_head, status: "pending"}`。

`buffer_id` 是 `"buffer-" + sha256_json({"preview_id": ...})`，所以对同一个 preview 反复调用
得到同一个 buffer，重试不会产生第二个 `buffer_id`。`formalize_candidate` 的
`merge_request_id` 参数就是它（`formalization.py:132-138` 用
`mapping_merge_request_buffer.buffer_id` join）。

验证：`cd sci-weave/centre-control/research-map && uv run --locked python -m unittest discover -s tests -q`
→ 124 passed, 5 skipped（新增 3 个用例：`test_create_merge_request_returns_buffer_id`、
`test_create_merge_request_is_idempotent`、`test_create_merge_request_rejects_unknown_preview`）。

补这张票的原因：Project Owner 套件的 `decide-candidate` 技能整条链依赖这个工具，
没有它那条技能写出来就是假的。
