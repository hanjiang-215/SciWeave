from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from gateway.app import create_app, make_handler
from gateway.runtime import RuntimeOutcome
from task_agent_worker.store import ExecutionStore, utc_now


class FakeCandidateQueue:
    def __init__(self, handler):
        self.handler = handler

    def deliver(self, candidate_id: str, event_type: str, event_id: str) -> dict[str, Any]:
        return self.handler(candidate_id, event_type, event_id)


class CentreAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(str(Path(self.temp.name) / "centre.sqlite3"), "test-token", "centre-agent")
        self.app.enable_test_runtime()
        self.queue = FakeCandidateQueue(self.app.submit_candidate_event)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.app.store.close()
        self.temp.cleanup()

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({
            "jsonrpc": "2.0", "id": "test", "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }).encode()
        request = urllib.request.Request(self.base + "/mcp", data=body, method="POST")
        request.add_header("Authorization", "Bearer test-token")
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read())
        content = payload["result"]["content"][0]["text"]
        return json.loads(content)

    def call_raw(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({
            "jsonrpc": "2.0", "id": "test", "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }).encode()
        request = urllib.request.Request(self.base + "/mcp", data=body, method="POST")
        request.add_header("Authorization", "Bearer test-token")
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    def wait_for(self, execution_id: str, status: str) -> dict[str, Any]:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            execution = self.app.query_execution(execution_id)
            if execution and execution["execution_status"] == status:
                return execution
            time.sleep(0.01)
        self.fail(f"{execution_id} did not reach {status}")

    def test_fake_candidate_event_runs_fixed_placeholder_to_completed(self) -> None:
        submitted = self.queue.deliver("candidate-1", "candidate_created", "event-1")
        execution = self.wait_for(submitted["execution_id"], "completed")
        self.assertEqual(execution["task_node_id"], "candidate-1")
        self.assertEqual(execution["result_summary"], "centre agent placeholder completed")
        self.assertIsNone(execution["pending_question"])

    def test_duplicate_event_does_not_create_second_execution(self) -> None:
        first = self.queue.deliver("candidate-1", "candidate_created", "event-1")
        duplicate = self.queue.deliver("candidate-1", "candidate_created", "event-1")
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["execution_id"], first["execution_id"])
        self.wait_for(first["execution_id"], "completed")
        with self.app.store.lock:
            count = self.app.store.connection.execute("SELECT COUNT(*) FROM execution_records").fetchone()[0]
        self.assertEqual(count, 1)

    def test_same_candidate_is_serialized(self) -> None:
        self.app.enable_test_runtime(duration_seconds=0.2)
        first = self.queue.deliver("candidate-1", "candidate_updated", "event-1")
        self.wait_for(first["execution_id"], "running")
        second = self.queue.deliver("candidate-1", "candidate_updated", "event-2")
        time.sleep(0.03)
        self.assertEqual(self.app.query_execution(second["execution_id"])["execution_status"], "queued")
        self.wait_for(first["execution_id"], "completed")
        self.wait_for(second["execution_id"], "completed")

    def test_centre_mcp_has_no_owner_submission_or_acceptance(self) -> None:
        tools = self.call("health")
        self.assertEqual(tools["status"], "ready")
        body = json.dumps({"jsonrpc": "2.0", "id": "tools", "method": "tools/list", "params": {}}).encode()
        request = urllib.request.Request(self.base + "/mcp", data=body, method="POST")
        request.add_header("Authorization", "Bearer test-token")
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request) as response:
            listed = json.loads(response.read())
        names = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertNotIn("submit_owner_command", names)
        self.assertNotIn("accept", names)

    def test_disposition_tools_require_their_arguments(self) -> None:
        for name in ("answer_question", "review_execution"):
            payload = self.call_raw(name, {"execution_id": "missing"})
            self.assertEqual(payload["error"]["code"], -32602)

    def test_answering_an_unknown_execution_is_not_found(self) -> None:
        result = self.call(
            "answer_question",
            {"execution_id": "missing", "answer": "v3", "idempotency_key": "key-1"},
        )
        self.assertEqual(result["error"]["code"], "not_found")

    def test_reviewing_an_unknown_execution_is_not_found(self) -> None:
        result = self.call(
            "review_execution",
            {
                "execution_id": "missing",
                "decision": "reject",
                "reason": "no evidence",
                "idempotency_key": "key-2",
            },
        )
        self.assertEqual(result["error"]["code"], "not_found")

    def test_dashboard_sources_requires_auth_and_returns_fragment(self) -> None:
        unauthenticated = urllib.request.Request(self.base + "/sources", method="GET")
        try:
            urllib.request.urlopen(unauthenticated)
            self.fail("unauthenticated /sources must be rejected")
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 401)

        self.queue.deliver("candidate-1", "candidate_created", "event-1")
        request = urllib.request.Request(self.base + "/sources", method="GET")
        request.add_header("Authorization", "Bearer test-token")
        with urllib.request.urlopen(request) as response:
            fragment = json.loads(response.read())
        self.assertEqual(fragment["sourceStatus"], "fresh")
        self.assertTrue(fragment["observedAt"])
        self.assertIn("executions", fragment)
        self.assertIn("services", fragment)
        execution = fragment["executions"][0]
        for key in ("id", "executionId", "taskId", "status", "trigger", "triggerRef", "updatedAt"):
            self.assertIn(key, execution)
        self.assertEqual(execution["taskId"], "candidate-1")
        self.assertEqual(execution["trigger"], "owner_command")
        # ai4-nvuj: events used to be a hard-coded empty list; they must now be
        # projected from the audit trail and stay inside the front-end vocabulary.
        self.assertIn("events", fragment)
        self.assertTrue(fragment["events"], "audit events must be projected, not hard-coded empty")
        for event in fragment["events"]:
            self.assertIn(
                event["type"],
                {"formal_release", "candidate_change", "message_received", "execution_completed", "mcp_failure"},
            )
            self.assertTrue(event["id"])
            self.assertTrue(event["occurredAt"])


if __name__ == "__main__":
    unittest.main()


class RuntimeConfigurationVisibilityTests(unittest.TestCase):
    """ai4-c61f: a runtime that failed to configure must not look healthy."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(
            str(Path(self.temp.name) / "centre.sqlite3"), "test-token", "centre-agent"
        )

    def tearDown(self) -> None:
        self.app.store.close()
        self.temp.cleanup()

    def test_unconfigured_runtime_is_reported_as_misconfigured(self) -> None:
        self.app.mark_runtime_misconfigured("api_key_missing")

        health = self.app.health()

        self.assertEqual(health["components"]["worker_runtime"], "misconfigured")
        self.assertIsNone(self.app.runtime)
        self.assertFalse(self.app.test_runtime_enabled)

    def test_dashboard_component_matches_health(self) -> None:
        self.app.mark_runtime_misconfigured("worker_settings_invalid: connection scope")

        services = {item["id"]: item for item in self.app.dashboard_sources()["services"]}

        # ai4-nvuj: the dashboard fragment speaks the vocabulary the web UI
        # validates, so a misconfigured runtime surfaces as "unavailable" rather
        # than reusing the health endpoint's internal "misconfigured" token.
        self.assertEqual(services["worker_runtime"]["status"], "unavailable")
        self.assertEqual(services["worker_runtime"]["role"], "centre-agent")
        self.assertTrue(services["worker_runtime"]["name"])
        for service in services.values():
            self.assertIn(service["role"], {"task-agent", "centre-agent"})
            self.assertIn(service["status"], {"online", "stale", "unavailable", "unknown"})

    def test_a_configured_runtime_reports_ready(self) -> None:
        self.app.enable_test_runtime()

        self.assertEqual(self.app.health()["components"]["worker_runtime"], "ready")

class PendingDispositionTests(unittest.TestCase):
    """ai4-k6m2: list_pending is the reviewer queue, not the whole history."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(
            str(Path(self.temp.name) / "centre.sqlite3"), "test-token", "centre-agent"
        )

    def tearDown(self) -> None:
        self.app.store.close()
        self.temp.cleanup()

    def _insert(self, execution_id: str, status: str) -> None:
        with self.app.store.transaction() as connection:
            connection.execute(
                """INSERT INTO execution_records
                   (execution_id, task_node_id, session_id, status, created_at, updated_at)
                   VALUES (?, 'node-1', 'session-1', ?, '2026-10-27T00:00:00', '2026-10-27T00:00:00')""",
                (execution_id, status),
            )

    def test_terminal_executions_are_not_pending(self) -> None:
        for index, status in enumerate(
            ["queued", "running", "waiting", "needs_revision", "human_takeover", "completed", "failed", "cancelled"]
        ):
            self._insert(f"exec-{index}", status)

        pending = {item["execution_status"] for item in self.app.list_pending()}

        self.assertEqual(
            pending, {"queued", "running", "waiting", "needs_revision", "human_takeover"}
        )

    def test_task_node_filter_still_applies(self) -> None:
        self._insert("exec-1", "queued")

        self.assertEqual(self.app.list_pending("node-1")[0]["execution_id"], "exec-1")
        self.assertEqual(self.app.list_pending("node-2"), [])

class CancelDoesNotGetOverwrittenTests(unittest.TestCase):
    """ai4-7oxu: a cancel that lands mid-run must survive the worker's final write."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "centre.sqlite3")
        self.store = ExecutionStore(self.db)
        self.store.initialize()
        now = utc_now()
        with self.store.transaction() as connection:
            connection.execute("INSERT INTO task_sessions VALUES ('node-1','sess-1',?,?)", (now, now))
            connection.execute("INSERT INTO callers VALUES ('owner-1',?)", (now,))
            connection.execute(
                "INSERT INTO owner_commands VALUES ('cmd-1','node-1','owner-1','idem-1','do it',?)",
                (now,),
            )
            connection.execute(
                """INSERT INTO execution_records
                   (execution_id, command_id, task_node_id, session_id, status, created_at, updated_at)
                   VALUES ('exec-1','cmd-1','node-1','sess-1','queued',?,?)""",
                (now, now),
            )

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_cancel_during_run_is_not_overwritten_by_completed(self) -> None:
        from gateway.app import run_worker_process

        db = self.db

        class CancellingRuntime:
            """Simulates cancel_execution landing while run() is in flight."""

            def run(self, request):
                other = ExecutionStore(db)
                try:
                    with other.transaction() as connection:
                        connection.execute(
                            "UPDATE execution_records SET status='cancelled' WHERE execution_id='exec-1'"
                        )
                finally:
                    other.close()
                return RuntimeOutcome("completed", result_summary="finished anyway")

            def resume(self, request):
                return self.run(request)

            def cancel(self, execution_id):
                return RuntimeOutcome("cancelled")

        run_worker_process(db, "exec-1", CancellingRuntime())

        with self.store.transaction() as connection:
            row = connection.execute(
                "SELECT status, result_summary FROM execution_records WHERE execution_id='exec-1'"
            ).fetchone()
            lease = connection.execute(
                "SELECT COUNT(*) FROM worker_leases WHERE execution_id='exec-1'"
            ).fetchone()[0]
        # The cancel wins: no completed/failed overwrite, and the lease is released.
        self.assertEqual(row["status"], "cancelled")
        self.assertIsNone(row["result_summary"])
        self.assertEqual(lease, 0)


class RecoverySweepTests(unittest.TestCase):
    """ai4-qt7x: a killed Worker must not leave an execution stuck forever."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "centre.sqlite3")
        self.store = ExecutionStore(self.db)
        self.store.initialize()
        self.now = utc_now()
        with self.store.transaction() as connection:
            connection.execute("INSERT INTO task_sessions VALUES ('node-1','sess-1',?,?)", (self.now, self.now))
            connection.execute("INSERT INTO callers VALUES ('owner-1',?)", (self.now,))
            connection.execute(
                "INSERT INTO owner_commands VALUES ('cmd-1','node-1','owner-1','idem-1','do it',?)",
                (self.now,),
            )
            connection.execute(
                """INSERT INTO execution_records
                   (execution_id, command_id, task_node_id, session_id, status, created_at, updated_at)
                   VALUES ('exec-1','cmd-1','node-1','sess-1','queued',?,?)""",
                (self.now, self.now),
            )

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def _execution(self, execution_id: str = "exec-1"):
        with self.store.transaction() as connection:
            return connection.execute(
                "SELECT status, error_summary FROM execution_records WHERE execution_id = ?", (execution_id,)
            ).fetchone()

    def test_orphan_lease_for_a_finished_execution_is_reaped(self) -> None:
        with self.store.transaction() as connection:
            connection.execute("INSERT INTO worker_leases VALUES ('node-1','exec-1',?)", (self.now,))
            connection.execute("UPDATE execution_records SET status='completed' WHERE execution_id='exec-1'")
        self.assertEqual(self.store.reap_orphan_leases(), 1)
        with self.store.transaction() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM worker_leases").fetchone()[0], 0)

    def test_stale_running_lease_is_failed_and_released(self) -> None:
        old = "2020-01-01T00:00:00+00:00"
        with self.store.transaction() as connection:
            connection.execute("INSERT INTO worker_leases VALUES ('node-1','exec-1',?)", (old,))
            connection.execute("UPDATE execution_records SET status='running' WHERE execution_id='exec-1'")
        reclaimed = self.store.reclaim_stale_leases(older_than_seconds=60)
        self.assertEqual(reclaimed, ["exec-1"])
        row = self._execution()
        self.assertEqual((row["status"], row["error_summary"]), ("failed", "worker_lost"))
        with self.store.transaction() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM worker_leases").fetchone()[0], 0)
            audit = connection.execute(
                "SELECT COUNT(*) FROM audit_events WHERE event_type='worker_lost' AND execution_id='exec-1'"
            ).fetchone()[0]
        self.assertEqual(audit, 1)

    def test_fresh_lease_is_left_alone(self) -> None:
        with self.store.transaction() as connection:
            connection.execute("INSERT INTO worker_leases VALUES ('node-1','exec-1',?)", (self.now,))
            connection.execute("UPDATE execution_records SET status='running' WHERE execution_id='exec-1'")
        self.assertEqual(self.store.reclaim_stale_leases(older_than_seconds=3600), [])
        self.assertEqual(self._execution()["status"], "running")

    def test_queued_execution_without_lease_is_redispatched_by_the_sweep(self) -> None:
        from gateway import app as gateway_app

        service = create_app(self.db, "test-token", "centre-agent")
        started: list[tuple[str, str]] = []

        class _Runtime:
            def run(self, request):
                return RuntimeOutcome("completed")

            def resume(self, request):
                return self.run(request)

            def cancel(self, execution_id):
                return RuntimeOutcome("cancelled")

        service.set_runtime(_Runtime())
        original = gateway_app.start_worker_process

        def recording(database, execution_id, runtime):
            started.append((database, execution_id))

        gateway_app.start_worker_process = recording
        try:
            report = gateway_app.sweep_once(service, stale_worker_seconds=3600)
        finally:
            gateway_app.start_worker_process = original
            service.store.close()

        self.assertEqual(report["redispatched"], ["exec-1"])
        self.assertEqual(started, [(self.db, "exec-1")])

    def test_sweep_does_not_dispatch_when_no_runtime_is_configured(self) -> None:
        from gateway import app as gateway_app

        service = create_app(self.db, "test-token", "centre-agent")
        started: list[str] = []
        original = gateway_app.start_worker_process
        gateway_app.start_worker_process = lambda database, execution_id, runtime: started.append(execution_id)
        try:
            report = gateway_app.sweep_once(service, stale_worker_seconds=3600)
        finally:
            gateway_app.start_worker_process = original
            service.store.close()
        self.assertEqual(report["redispatched"], [])
        self.assertEqual(started, [])
