---
id: ai4-heb2
status: closed
deps: []
links: []
created: 2026-10-29T02:55:01Z
type: chore
priority: 2
assignee: hanjiang
---
# worker 运行时异常只报错误码、不记堆栈；死代码 step()

审查报告第三节：runtime._execute 与 passthrough 异常一律吞成 fast_agent_runtime_error，丢堆栈无日志；另有未被调用的 async def step()。改为 logger.exception 记录执行 id 与堆栈，保留原 error_summary 语义；step() 补注释说明其为装饰器入口。

## Acceptance Criteria

1) 两类失败都 logger.exception 记录；2) error_summary 不变；3) 测试断言有堆栈日志；4) 无死代码

