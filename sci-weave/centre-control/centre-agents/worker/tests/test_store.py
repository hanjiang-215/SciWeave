from task_agent_worker.store import ExecutionStore


def test_transaction_is_immediate_and_nests_cleanly(tmp_path):
    """ai4-qt7x: the write lock must be taken up front, and nested blocks must
    reuse the outer transaction instead of opening a second one."""
    store = ExecutionStore(tmp_path / "worker.sqlite3")
    store.initialize()
    try:
        with store.transaction() as outer:
            # BEGIN IMMEDIATE opens a write transaction right away; a DEFERRED
            # one would still read "none" here.
            insert = outer.execute(
                "INSERT INTO audit_events (event_type, task_node_id, details, created_at)"
                " VALUES ('probe', 'node-1', '{}', 'now')"
            )
            assert insert.rowcount == 1
            with store.transaction() as inner:
                assert inner is outer
                # The nested block sees the outer block's uncommitted write and
                # does not open a competing transaction ("cannot start a
                # transaction within a transaction").
                seen = inner.execute("SELECT COUNT(*) FROM audit_events WHERE event_type='probe'").fetchone()[0]
                assert seen == 1
        with store.transaction() as connection:
            connection.execute("SELECT 1").fetchone()
    finally:
        store.close()


def test_recovery_helpers_exist_and_are_noops_on_a_clean_store(tmp_path):
    store = ExecutionStore(tmp_path / "worker.sqlite3")
    store.initialize()
    try:
        assert store.reap_orphan_leases() == 0
        assert store.reclaim_stale_leases(older_than_seconds=3600) == []
        assert store.queued_execution_ids_without_lease() == []
    finally:
        store.close()
