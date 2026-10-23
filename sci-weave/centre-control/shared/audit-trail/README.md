# SciWeave audit-trail

`audit_trail` 是中央服务使用的仅追加调用账本，使用 Python 标准库和 SQLite。

## 使用

```python
from audit_trail import CallRecord, init_audit_table, open_connection, record_attempted

conn = open_connection("/path/to/audit.sqlite")
init_audit_table(conn)

record_attempted(conn, CallRecord(
    caller_id="user-1",
    channel_id="web",
    caller_type="human",
    service="mapping-mcp",
    tool="get_proposal",
    target_object_type="proposal",
    target_object_id="p-1",
    args_digest="sha256:...",
    refs='{"revision":"r1"}',
))
```

`record_attempted` 用于读调用，写入失败时记录警告并返回 `None`，不打断业务读取。写调用使用 `begin_call`、`finish_call` 或 `call_scope`；开始阶段写入失败会抛出 `AuditUnavailableError`。包不读取环境变量，调用方负责传入数据库路径并管理连接生命周期。

运行测试：

```bash
uv run --extra test pytest
```
