"""审计写入入口。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from importlib import resources

from audit_trail.events import AuditEvent, TransactionRequiredError

_SCHEMA_SQL = resources.files("audit_trail").joinpath("schema.sql").read_text(
    encoding="utf-8"
)

_INSERT_SQL = """
INSERT INTO audit_event (
    event_id, occurred_at, actor_id, actor_type, operation,
    target_object_type, target_object_id, result,
    previous_state, next_state, reason, base_revision, candidate_revision,
    proposal_id, task_id, resource_id, formal_revision_id, merge_request_id, refs
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def init_audit_table(conn: sqlite3.Connection) -> None:
    """在调用方的 SQLite 连接上建立标准审计表。"""
    conn.execute(_SCHEMA_SQL)


def write_audit_event(conn: sqlite3.Connection, event: AuditEvent) -> str:
    """追加一条审计事件，返回生成的 ``event_id``。

    必须在调用方自己的 SQLite 事务内调用；连接不在事务里时抛
    :class:`TransactionRequiredError`。字段缺失或枚举非法时抛
    :class:`AuditValidationError`。
    """
    if not isinstance(conn, sqlite3.Connection):
        raise TypeError("conn must be a sqlite3.Connection")
    if not conn.in_transaction:
        raise TransactionRequiredError(
            "write_audit_event must be called inside the caller's SQLite transaction"
        )

    event.validate()

    event_id = str(uuid.uuid4())
    occurred_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    refs_json = (
        json.dumps(event.refs, ensure_ascii=False, sort_keys=True)
        if event.refs is not None
        else None
    )

    conn.execute(
        _INSERT_SQL,
        (
            event_id,
            occurred_at,
            event.actor_id,
            event.actor_type,
            event.operation,
            event.target_object_type,
            event.target_object_id,
            event.result,
            event.previous_state,
            event.next_state,
            event.reason,
            event.base_revision,
            event.candidate_revision,
            event.proposal_id,
            event.task_id,
            event.resource_id,
            event.formal_revision_id,
            event.merge_request_id,
            refs_json,
        ),
    )
    return event_id
