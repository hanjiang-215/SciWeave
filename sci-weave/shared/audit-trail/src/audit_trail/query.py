"""审计事件查询。只读，与写入分离。"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

_SELECT_SQL = """
SELECT event_id, occurred_at, actor_id, actor_type, operation,
       target_object_type, target_object_id, result,
       previous_state, next_state, reason, base_revision, candidate_revision,
       proposal_id, task_id, resource_id, formal_revision_id, merge_request_id, refs
FROM audit_event
"""


def query_audit_events(
    conn: sqlite3.Connection,
    *,
    task_id: str | None = None,
    proposal_id: str | None = None,
    formal_revision_id: str | None = None,
    occurred_after: str | None = None,
    occurred_before: str | None = None,
) -> list[dict[str, Any]]:
    """按任务、Proposal、正式版本、时间过滤审计事件，时间倒序返回。

    全部参数可选；不传任何过滤条件时返回全部事件。
    """
    clauses: list[str] = []
    params: list[str] = []

    if task_id is not None:
        clauses.append("task_id = ?")
        params.append(task_id)
    if proposal_id is not None:
        clauses.append("proposal_id = ?")
        params.append(proposal_id)
    if formal_revision_id is not None:
        clauses.append("formal_revision_id = ?")
        params.append(formal_revision_id)
    if occurred_after is not None:
        clauses.append("occurred_at > ?")
        params.append(occurred_after)
    if occurred_before is not None:
        clauses.append("occurred_at < ?")
        params.append(occurred_before)

    sql = _SELECT_SQL
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY occurred_at DESC, rowid DESC"

    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "event_id": row[0],
            "occurred_at": row[1],
            "actor_id": row[2],
            "actor_type": row[3],
            "operation": row[4],
            "target_object_type": row[5],
            "target_object_id": row[6],
            "result": row[7],
            "previous_state": row[8],
            "next_state": row[9],
            "reason": row[10],
            "base_revision": row[11],
            "candidate_revision": row[12],
            "proposal_id": row[13],
            "task_id": row[14],
            "resource_id": row[15],
            "formal_revision_id": row[16],
            "merge_request_id": row[17],
            "refs": json.loads(row[18]) if row[18] is not None else None,
        }
        for row in rows
    ]
