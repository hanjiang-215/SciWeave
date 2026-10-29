---
id: ai4-72pa
status: closed
deps: []
links: []
created: 2026-10-29T02:23:30Z
type: bug
priority: 1
assignee: hanjiang
---
# dashboard 源请求跟随 302 会把 bearer token 转发给跳转目标

审查报告 S4 复核并实测：Python 3.11 urlopen 在 302 到另一个源时原样转发 Authorization。config 只校验 http(s) 与无内嵌凭据，不校验最终地址。

## Acceptance Criteria

1) 拒绝重定向或以新 reason_code 报错；2) 校验最终 URL 与配置同源；3) 测试：跳转源被判为不可用且不请求跳转目标；4) 公开错误信息不泄漏目标地址

