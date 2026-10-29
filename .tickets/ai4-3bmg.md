---
id: ai4-3bmg
status: closed
deps: []
links: []
created: 2026-10-29T05:04:43Z
type: bug
priority: 1
assignee: hanjiang
---
# wiki 候选提交: _request 走 3 参 GET opener 导致 TypeError

E2E 复验(技术缺陷报告 缺陷1)：_request(self,method,url,body) 需发送任意 method+body，却路由到 Opener=Callable[[url,headers,timeout]](3 参仅 GET)，__init__ 默认 _request_opener=self._opener，于是每次候选提交首次 _candidate_branches() GET 即 TypeError，被 except 吞成 store_result_unknown，Wiki 治理链完全不可用。修复：保留可注入的 5 参 request_opener，默认实现自建 Request 并 urlopen。

## Acceptance Criteria

1) _request 默认 opener 为 5 参(method,url,headers,body,timeout)；2) 可注入同签名 opener 供测试；3) 读路径 3 参 opener 不变；4) 回归测试覆盖；5) wiki 全量通过

