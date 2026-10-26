---
id: ai4-3u7x
status: closed
deps: []
links: [ai4-dobw, ai4-m1d1]
created: 2026-10-25T13:40:00Z
type: chore
priority: 3
assignee: hanjiang
parent: ai4-dobw
tags: [centre-control, email-service, tests, verification]
---
# 修复 email-service 测试夹具未同步新增重试配置项

`ai4-dobw`(补齐邮件健康分项、运维查询与调用方约束)为 `config.py` 新增了 5 个必填环境变量,但 `tests/test_http.py`、`tests/test_invalid.py`、`tests/test_idempotency.py`、`tests/test_constraints.py` 的 fixture/helper 未同步注入,导致测试在 setup 阶段直接 `ValueError` 挂红。本票记录修复事实与验证证据。

## Design

根因:新增必填配置 `SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS`、`SCIWEAVE_EMAIL_RETRY_MULTIPLIER`、`SCIWEAVE_EMAIL_RETRY_MAX_SECONDS`、`SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS`、`SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS` 进入 `config.from_environment()` 的 required 集合后,四个测试文件的本地配置构造没有跟上。`test_retry.py` 已带这些变量,不受影响。

修复:在四个测试文件的配置段补入与 `test_retry.py::_configure` 相同的默认值(`initial=1`、`multiplier=2`、`max=60`、`poll=0.05`、`sending_timeout=30`;`test_constraints.py` 用其已有 `initial=30` 上下文,补其余三项)。

## Acceptance Criteria

- [x] 四个测试文件的 fixture/helper 均注入 5 个重试配置项,不再因 `from_environment()` 抛 `ValueError`
- [x] `sci-weave/centre-control/email-service` 全部测试通过
- [x] 不改变产品代码行为,仅同步测试配置

## Notes

**2026-10-25 修复与验证（hanjiang）**

身份核对:本票 assignee 为 hanjiang,当前分支 `feature/hanjiang`、`git config user.name=hanjiang`,一致。

- 修复前:9 failed + 13 passed + 37 errors(2026-10-25 全量复跑实测)。
- 修复后:59 passed in 53.10s(2026-10-25 全量复跑实测,退出码 0)。
- 提交:`c0fc1ce`(feature/hanjiang,4 files changed, +18)。
- 涉及文件:`tests/test_http.py`、`tests/test_invalid.py`、`tests/test_idempotency.py`、`tests/test_constraints.py`。
- 关联:`ai4-dobw`(新增必填配置项的源票,closed)与 `ai4-m1d1`(email-service 实现票,closed)。本票不修改这两张他人 closed 票的内容,仅承载修复事实。
- 本票与实现改动无产品语义影响,作 chore 关闭。
