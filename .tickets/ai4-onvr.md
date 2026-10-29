---
id: ai4-onvr
status: closed
deps: []
links: []
created: 2026-10-29T01:43:50Z
type: bug
priority: 2
assignee: hanjiang
---
# 可靠性批量修复：吞错加日志/事务回滚/超时/前端竞态/NaN decode

技术审查 P2 批量：coordinator service.py:524-525 冗余条件；main.py:195-204 失败无死信；management_mcp.py:213 异常归一；store.py:238 done 静默；email service.py:397 裸 except 吞错无日志；registry service.py:338 BEGIN 后非 sqlite 异常不回滚；dashboard aggregator.py:33 无总超时 + http_server.py:30/aggregator.py:43 吞错无日志；message-envelope decode 未拒 NaN；web-ui dashboard.ts:29 abort 覆盖 error；subscriber cli.py:103 宽兜底注释。

## Acceptance Criteria

各点修复并补日志；registry 事务异常回滚；dashboard 单 source 有总超时；message-envelope decode 拒 NaN/Infinity；web-ui abort 不置 error；全部测试绿。
## Notes

2026-10-29 hanjiang：P2 批次已修复，涉及提交 094139、37e94fa、d22e1d4、6f4969a、293d793、172eb5。

- coordinator：management_mcp 区分 ValueError → 
ot_a_root_node；done 状态被拦下时记日志；治理事件处理失败日志带 topic/partition/offset 便于重放。
- email-service：未预期发件异常记 logger.exception 并在 summary 标注异常类型（不泄漏正文/凭据）。
- registry：_write 的 BEGIN 对任意异常都回滚，避免连接残留在事务中。
- dashboard-api：新增整次快照总预算 SCIWEAVE_DASHBOARD_SNAPSHOT_DEADLINE_SECONDS（默认 10s），超时源报 source_timeout 且不影响其余源；聚合器与 HTTP 处理器的裸 except 补日志。
- message-envelope：decode 用 parse_constant 拒绝 NaN/Infinity，与 encode 的 llow_nan=False 对称；buffer 的 canonical_json 同样改 llow_nan=False。
- subscriber：un_loop 按 target 隔离 runner 异常，一个目标失败不再中断整批。
- web-ui：dashboard store 不再把 AbortError 当失败（旧请求被取消时不清空快照、不弹错误）。

验证：coordinator 92、email 115、registry 17、dashboard 19、message-envelope 88、subscriber 33、buffer 30、web-ui 30（vitest）+ ue-tsc 通过。

未纳入本批次（原报告“疑似/低优先级”）：S1 多进程 SQLite 互斥、S3 operator 读取范围、S4 内网 URL allowlist、S5 收件人计数、S6 FastMCP 猴补丁、S7 token 常数时间比较、S8 空 topic 静默、S9 executor 字段语义、S10 owner_event CAS，以及低优先级易用性条目。以上仍需单独评估，非本次“确认缺陷”范围。