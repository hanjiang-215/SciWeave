---
id: ai4-4bxp
status: closed
deps: []
links: [ai4-te1v]
created: 2026-10-27T11:33:46Z
type: task
priority: 2
assignee: hanjiang
tags: [message-envelope, protocol, design]
---
# message-envelope 协议包零生产引用：登记延后决策与接线前置条件

`shared/message-envelope` 有 87 项测试全绿，但**生产代码零引用**：

```text
git grep -n message_envelope -- '*.py' ':!*/tests/*'   → 无命中
```

coordinator 的 `adapter_publisher.py:52` 手搓 `dict` 发 `task_handoff_ready`，`gateway/ingest`、`toolkits/.../service-template` 同样各自手搓。信封包里定义的 `schema_version`、`message_id`、`dedupe_key`、`occurred_at` / `published_at`、`producer`、`routing` 一个都没在线上出现过。

这与 10-22 审查时 `audit-trail` 的处境相同，区别是 `audit-trail` 后来接上了（research-map / research-wiki / registry / email-service 四个 path 依赖），信封包没接。

## 为什么本轮不接线

接线不是「换一个 import」：`Envelope` 的字段集（`message_id` / `dedupe_key` / `schema_version` / 两个时间戳 / `producer` / `routing` / `payload`）与当前线格式（扁平七字段）不兼容，改完就是一次协议迁移，端侧 subscriber 的解析、去重键与既有消息兼容性都要一起动。距作品提交 4 天，改坏消息通路的代价远大于收益。

## 本票要做的

把这个判断写进文档与票里，让下一个读代码的人知道「这是有意延后，不是漏了」，并明确接线的前置条件。不写实现代码。

## Acceptance Criteria

- [x] `shared/message-envelope/README.md` 写明「当前无生产调用方」与原因，避免被读成已生效的协议约束。
- [x] 记录接线的前置条件（端侧 subscriber 解析改造、去重键来源、与既有扁平消息的兼容窗口）与建议顺序。
- [x] 与 `ai4-8pvm`、`ai4-te1v` 建立 links，便于从协议票找到本决策。


## Notes

**2026-10-27T12:01:12Z**

## 2026-10-27 登记决策

按本票计划只登记、不改实现（接线是协议迁移，距离提交 4 天，改坏消息通路的成本高于收益）：

1. **`shared/message-envelope/README.md`** 新增「当前状态：没有生产调用方」一节：`git grep message_envelope -- '*.py' ':!*/tests/*'` 无命中，线上仍是扁平 dict；两张对照表说明 `Envelope` 字段集与现状的差异（差额字段包括 `upstream_source_refs`、`dependency_edge_version_refs`、`executor_ref_snapshot`），并给出接线前置条件与建议顺序（补齐引用字段 → 定 dedupe_key 来源 → 端侧 subscriber 兼容窗口 → 切生产方）。
2. **links**：`ai4-te1v`（统一信封表）链接已建。`ai4-8pvm` 的 assignee 是 Frank Qi，按属人修改权不能直接改他的票，因此不在他票上建 link；这里文字登记关联关系（`ai4-8pvm` = 端侧交接消息协议）。`ai4-3zxu` 为信封实现票。
3. **README 其余行**：`centre-control/README.md` 里 message-envelope 行已注明当前状态与决策票。

证据：`git grep message_envelope`（修订前后）输出见本票正文；接线前置条件已随文档入库。
