import sqlite3

import pytest

from audit_trail import (
    AuditUnavailableError,
    AuditValidationError,
    CallRecord,
    begin_call,
    call_scope,
    finish_call,
    find_unfinished_calls,
    init_audit_table,
    open_connection,
    query_audit_calls,
    record_attempted,
)


def make_record(**overrides):
    values = {
        "caller_id": "user-1",
        "channel_id": "web",
        "caller_type": "human",
        "service": "mapping-mcp",
        "tool": "get_proposal",
        "target_object_type": "proposal",
        "target_object_id": "p-1",
        "args_digest": "sha256:abc",
        "refs": '{"revision":"r1"}',
    }
    values.update(overrides)
    return CallRecord(**values)


def make_connection():
    conn = open_connection(":memory:")
    init_audit_table(conn)
    return conn


def test_open_and_init_are_path_based_and_idempotent(tmp_path):
    conn = open_connection(str(tmp_path / "audit.sqlite"))
    init_audit_table(conn)
    init_audit_table(conn)

    columns = [row[1] for row in conn.execute("PRAGMA table_info(audit_call)")]
    assert columns == [
        "call_id", "occurred_at", "caller_id", "channel_id", "caller_type",
        "service", "tool", "phase", "result", "target_object_type",
        "target_object_id", "args_digest", "error_code", "duration_ms", "refs",
    ]
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(audit_call)")}
    assert len(indexes) >= 3
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_attempted_call_can_be_read_back_with_digest_and_refs():
    conn = make_connection()
    record = make_record()

    call_id = record_attempted(conn, record)
    rows = query_audit_calls(conn, caller_id="user-1")

    assert call_id
    assert len(rows) == 1
    assert rows[0]["call_id"] == call_id
    assert rows[0]["phase"] == "attempted"
    assert rows[0]["result"] == "unknown"
    assert rows[0]["args_digest"] == "sha256:abc"
    assert rows[0]["refs"] == '{"revision":"r1"}'


def test_memory_database_downgrades_wal():
    conn = open_connection(":memory:", journal_mode="WAL")
    init_audit_table(conn)


def test_open_failure_is_unavailable(tmp_path):
    with pytest.raises(AuditUnavailableError):
        open_connection(str(tmp_path / "missing" / "audit.sqlite"))


def test_attempted_write_is_fail_open():
    conn = make_connection()
    conn.close()

    assert record_attempted(conn, make_record()) is None


def test_invalid_record_is_validation_error():
    with pytest.raises(AuditValidationError):
        CallRecord(
            caller_id="u", channel_id="c", caller_type="robot",
            service="s", tool="t",
        )


def test_begin_and_finish_share_call_id_and_close_unfinished_call():
    conn = make_connection()
    call_id = begin_call(conn, make_record(service="buffer", tool="write"))

    unfinished = find_unfinished_calls(conn)
    assert [row["call_id"] for row in unfinished] == [call_id]

    finish_call(conn, call_id, result="ok", duration_ms=12)
    rows = query_audit_calls(conn, service="buffer")
    assert [(row["phase"], row["call_id"]) for row in rows] == [
        ("completed", call_id), ("invoked", call_id)
    ]
    assert find_unfinished_calls(conn) == []


def test_begin_fails_closed_when_database_is_unavailable():
    conn = make_connection()
    conn.close()

    with pytest.raises(AuditUnavailableError):
        begin_call(conn, make_record())


def test_finish_rejects_missing_duplicate_and_attempted_calls():
    conn = make_connection()
    with pytest.raises(AuditValidationError):
        finish_call(conn, "missing", result="ok")

    attempted_id = record_attempted(conn, make_record())
    with pytest.raises(AuditValidationError):
        finish_call(conn, attempted_id, result="ok")

    call_id = begin_call(conn, make_record())
    finish_call(conn, call_id, result="error", error_code="conflict")
    with pytest.raises(AuditValidationError):
        finish_call(conn, call_id, result="ok")


def test_audit_append_rejects_existing_business_transaction():
    conn = make_connection()
    conn.execute("BEGIN")
    with pytest.raises(AuditValidationError):
        record_attempted(conn, make_record())
    conn.rollback()


def test_call_scope_records_success_and_reraises_failure():
    conn = make_connection()
    with call_scope(conn, make_record()) as call_id:
        assert call_id
    assert query_audit_calls(conn)[0]["result"] == "ok"

    with pytest.raises(RuntimeError, match="boom"):
        with call_scope(conn, make_record(tool="fail")):
            raise RuntimeError("boom")
    rows = query_audit_calls(conn, tool="fail")
    assert rows[0]["result"] == "error"
    assert rows[0]["error_code"] is None
    assert rows[0]["duration_ms"] is not None


def test_query_filters_and_stable_reverse_order():
    conn = make_connection()
    first = record_attempted(conn, make_record(caller_id="u1", channel_id="c1"))
    second = record_attempted(conn, make_record(caller_id="u2", channel_id="c2", target_object_id="p-2"))
    assert first and second

    assert [row["call_id"] for row in query_audit_calls(conn, caller_id="u2")] == [second]
    assert [row["call_id"] for row in query_audit_calls(conn, channel_id="c1")] == [first]
    assert [row["call_id"] for row in query_audit_calls(conn, target_object_id="p-2")] == [second]
    assert [row["call_id"] for row in query_audit_calls(conn, result="unknown")] == [second, first]
    all_rows = query_audit_calls(conn)
    assert [row["call_id"] for row in all_rows] == [second, first]
    assert query_audit_calls(conn, occurred_after=all_rows[-1]["occurred_at"]) == all_rows


def test_query_rejects_non_string_filters():
    conn = make_connection()
    with pytest.raises(AuditValidationError):
        query_audit_calls(conn, caller_id=123)


def test_no_update_or_delete_api_is_exposed():
    import audit_trail

    assert "update" not in audit_trail.__all__
    assert "delete" not in audit_trail.__all__
