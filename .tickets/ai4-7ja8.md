---
id: ai4-7ja8
status: open
deps: []
links: []
created: 2026-10-28T07:32:45Z
type: bug
priority: 1
assignee: Frank Qi
parent: ai4-yidf
tags: [centre-control, centre-agents, deployment, observability]
---
# gateway/mcp 用占位符 API key 启动会直接崩，而不是降级为 misconfigured

`centre-gateway-mcp`（8760）的启动路径上，只有「key 为空」是优雅降级，「key 非空但不合法」会直接让整个网关崩掉。

`gateway/mcp/src/gateway/cli.py:33-66` 的结构是：

```python
settings.validate_runtime(require_api_key=False)      # 不校验 key，只校验 home/session/scope
if settings.api_key:                                  # 占位符字符串也是真值
    try:
        app.enable_fast_agent_deepseek_runtime(settings)   # 内部第一行才校验 key
    except CentreConfigError:                              # ← 只接这一种
        app.mark_runtime_misconfigured(...)
```

`enable_fast_agent_deepseek_runtime` → `FastAgentDeepSeekRuntime.__init__` 的第一行是 `settings.validate_for_model_call()`，抛的是 **`ValueError`**，不在被捕获的类型里，于是穿透 `main()`，进程退出、supervisord 反复重启。

触发条件就是 `.env.example` 的默认值：`DEEPSEEK_API_KEY=replace-with-your-deepseek-api-key`。`validate_runtime` 里专门有 `startswith("replace-with-")` 的判定，说明「忘了改名」是预期会发生的操作失误；但这个判定只会在构造 runtime 时才执行，此时已经没人接住了。

后果是排障方向被带偏：README 与 compose 注释都写着「不配 key 也能起，只是标成 misconfigured」，运维看到 8760 起不来会先去查端口、查 SQLite、查 compose 变量，而真正的原因是一句 `DEEPSEEK_API_KEY must be configured` 埋在 supervisord 的 FATAL 日志里（且每 3 秒重刷一次）。

## Acceptance Criteria

- [ ] 用 `DEEPSEEK_API_KEY=replace-with-your-deepseek-api-key` 启动 `centre-gateway-mcp`，进程不退出，`/health` 返回且 `worker_runtime` 为 `unavailable`（即 `misconfigured`）
- [ ] `runtime_misconfigured` 的原因字符串明确指出是 API key 而非目录或定义层问题，与「key 为空」时的 `api_key_missing` 可区分
- [ ] 回归用例覆盖三种输入：key 为空、key 是占位符、key 格式非法；三者都不得让进程退出
- [ ] `gateway/subscriber` 的行为不被改动：它本就该在无 key 且未开 passthrough 时 FATAL（ai4-c61f 的裁决），本票只修 8760 这一侧
- [ ] `docs/` 或 README 里「不配也能起」这句话补上边界：空值降级、占位符与非法值同样降级（修完之后）


## Notes

**2026-10-28T07:33:04Z**

**2026-10-28T07:36:00Z（复现）**

已在本地 venv 里复现，不需要容器：

```bash
cd sci-weave/centre-control/centre-agents
DEEPSEEK_API_KEY=replace-with-your-deepseek-api-key \
DEEPSEEK_BASE_URL=https://api.deepseek.com SCIWEAVE_WORKER_MODEL=deepseek-chat \
SCIWEAVE_WORKER_HOME=/tmp/wh SCIWEAVE_WORKER_SESSION_DIR=sessions \
SCIWEAVE_WORKER_CONNECTION_SCOPE=centre-agent \
uv run --project . python - <<'PY'
from task_agent_worker.config import WorkerSettings
from task_agent_worker.assembly import CentreConfigError
from task_agent_worker.runtime import FastAgentDeepSeekRuntime
s = WorkerSettings.from_environment()
s.validate_runtime(require_api_key=False)
print("ok, api_key truthy:", bool(s.api_key))
try:
    FastAgentDeepSeekRuntime(s)
except CentreConfigError as e:
    print("caught CentreConfigError ->", e)
except ValueError as e:
    print("ESCAPES as ValueError:", e)
PY
```

输出：

```
validate_runtime(require_api_key=False) -> OK, api_key truthy: True
ESCAPES as ValueError (not caught by cli.py): DEEPSEEK_API_KEY must be configured
```

即：`cli.py` 的第一步放行、第二步抛 `ValueError`、`except CentreConfigError` 接不住。这与本票描述一致。

**修法倾向**（留给实现时定，不写进验收）：把 `enable_fast_agent_deepseek_runtime` 的异常捕获放宽到 `(CentreConfigError, ValueError)`，并在 `mark_runtime_misconfigured` 里用不同 reason 前缀区分 `api_key_missing`（空）与 `api_key_invalid: ...`（非空但不合法）。不采用「提前调 `validate_for_model_call` 再分支」的写法：那会把「key 合法性」与「定义层可读性」两次校验的先后顺序变成新的隐式契约。
