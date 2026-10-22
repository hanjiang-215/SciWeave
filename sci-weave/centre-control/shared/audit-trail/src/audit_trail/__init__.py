"""SciWeave 中央留痕工具：统一审计接口。

所有改动正式事实的组件在写事实的同一个 SQLite 事务里调用
:func:`write_audit_event`。只追加，不提供更新或删除。
"""

from audit_trail.writer import init_audit_table, write_audit_event
from audit_trail.events import AuditEvent, AuditValidationError, TransactionRequiredError
from audit_trail.query import query_audit_events

__all__ = [
    "AuditEvent",
    "AuditValidationError",
    "TransactionRequiredError",
    "init_audit_table",
    "write_audit_event",
    "query_audit_events",
]
