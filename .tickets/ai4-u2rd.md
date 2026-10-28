---
id: ai4-u2rd
status: closed
deps: []
links: [ai4-91tk]
created: 2026-10-27T11:33:33Z
type: bug
priority: 1
assignee: hanjiang
tags: [research-wiki, test, governance]
---
# research-wiki 同名测试覆盖，通知失败与审计断言从未执行

`sci-weave/centre-control/research-wiki/tests/test_formalization.py` 里 `test_same_operation_is_rejected_when_owner_approval_identity_changes` 定义了两次（L63、L101），后者覆盖前者。

L63 那一段不是独立用例，是一次坏掉的编辑：它的函数体缩进 12 空格，直接引用上一条用例 `test_requires_owner_approval_and_activates_only_after_exact_store_readback` 的局部变量 `db`，没有自己的 `TemporaryDirectory`。就算不被覆盖也会 `NameError`。

被吞掉的断言正好守着失败路径：

```python
self.assertEqual((op_row[notification_status], op_row[notification_reason]), (failed, notification_failed))
self.assertGreaterEqual(audit_count, 1)
self.assertIn(formalization_activated, audit_actions)
self.assertEqual(result_row[resource_approval_map], {})
self.assertEqual(op_approvals, {})
```

因此「通知发送失败仍完成正式化并留痕」这条行为目前没有任何测试在守，`136 passed` 里也少了它。10-22 的审查已提过，至今未修。

## Acceptance Criteria

- [x] 两段断言合并进它们真正归属的用例，函数体不再引用外部局部变量；全文件无重名测试方法。
- [x] 「通知失败 → `notification_status=failed` / `notification_reason=notification_failed` → 正式化仍成功 → 审计含 `formalization_activated`」这条链路有断言覆盖，且**确实被执行**（合并不新增用例，确认方式见 Notes：故意改错断言值应使测试变红）。
- [x] `uv run --with pytest --with pytest-asyncio pytest tests -q` 全绿；连真实 TerminusDB 的集成用例同样全绿。


## Notes

**2026-10-27T11:51:21Z**

## 2026-10-27 修复

**复核结论**：L63 那段不是独立用例，是一次坏掉的编辑——函数体缩进 12 空格，直接引用上一条用例 `test_requires_owner_approval_and_activates_only_after_exact_store_readback` 的局部变量 `db`，自己没有 `TemporaryDirectory`。即使不被同名定义覆盖也会 `NameError`。L101 的同名定义把它整个屏蔽，所以这 11 行断言从未执行。

**改动**（`sci-weave/centre-control/research-wiki/tests/test_formalization.py`）：删掉 L63 那个幻影 `def`，把它的断言体缩进回 8 空格，接在上一条用例末尾——它们本来就是那条用例的后半段（`fresh-op` 的执行结果、通知失败状态、审计动作）。全文件现在无重名方法。

**验证**：
1. `pytest tests/test_formalization.py -q` → 9 passed。
2. 证明断言确实在执行（而不是又一次空转）：把恢复的断言里 `(failed,notification_failed)` 故意改成 `(failed,PROBE_WRONG_REASON)`，测试立即红并打印
   `AssertionError: Tuples differ: ('failed', 'notification_failed') != ('failed', 'PROBE_WRONG_REASON')`；还原后 9 passed。
3. 全量矩阵：research-wiki 136 passed / 12 skipped，与修复前一致——符合预期，因为修的是断言覆盖而不是用例数量。

**票面更正**：本票 AC 第 2 条原写「用例数较修前 +1」，与事实不符（合并不新增测试方法，只让原有断言真正执行）。已按实际改成断言覆盖，并在本条记录更正原因，不改动 AC 其余部分。
