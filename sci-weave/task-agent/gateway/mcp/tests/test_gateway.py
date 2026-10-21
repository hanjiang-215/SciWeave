from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from gateway.app import create_app, make_handler


class GatewayMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(
            str(Path(self.temp.name) / "gateway.sqlite3"), "test-token", "local-owner"
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.app.store.close()
        self.temp.cleanup()

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        token: str | None = "test-token",
    ) -> tuple[int, dict[str, Any]]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        if token is not None:
            request.add_header("Authorization", f"Bearer {token}")
        if data:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def mcp_call(
        self, method: str, params: dict[str, Any] | None = None, token: str | None = "test-token"
    ) -> tuple[int, dict[str, Any]]:
        return self.request(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "id": "test-request", "method": method, "params": params or {}},
            token,
        )

    def tool_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.assertIn("result", payload)
        content = payload["result"]["content"]
        self.assertEqual(len(content), 1)
        return json.loads(content[0]["text"])

    def test_authenticated_mcp_submits_queries_and_deduplicates_owner_commands(self) -> None:
        status, initialized = self.mcp_call(
            "initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test"}}
        )
        self.assertEqual(status, 200)
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-03-26")

        status, submitted = self.mcp_call(
            "tools/call",
            {
                "name": "submit_owner_command",
                "arguments": {
                    "task_node_id": "node-1",
                    "command": "inspect",
                    "idempotency_key": "idem-1",
                },
            },
        )
        self.assertEqual(status, 200)
        first = self.tool_result(submitted)
        self.assertEqual(first["execution_status"], "queued")
        self.assertFalse(first["duplicate"])

        status, repeated = self.mcp_call(
            "tools/call",
            {
                "name": "submit_owner_command",
                "arguments": {
                    "task_node_id": "node-1",
                    "command": "ignored-on-retry",
                    "idempotency_key": "idem-1",
                },
            },
        )
        self.assertEqual(status, 200)
        duplicate = self.tool_result(repeated)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["execution_id"], first["execution_id"])

        status, queried = self.mcp_call(
            "tools/call",
            {"name": "query_execution", "arguments": {"execution_id": first["execution_id"]}},
        )
        self.assertEqual(status, 200)
        execution = self.tool_result(queried)
        self.assertEqual(execution["task_node_id"], "node-1")
        self.assertEqual(execution["execution_status"], "queued")
        self.assertEqual(execution["caller_id"], "local-owner")

    def test_unauthenticated_requests_cannot_create_facts_and_loopback_health_is_minimal(self) -> None:
        status, health = self.request("GET", "/health", token=None)
        self.assertEqual((status, health), (200, {"status": "ready", "gateway_api_version": "v1"}))

        status, rejected = self.mcp_call(
            "tools/call",
            {
                "name": "submit_owner_command",
                "arguments": {
                    "task_node_id": "node-1",
                    "command": "inspect",
                    "idempotency_key": "rejected-key",
                },
            },
            token=None,
        )
        self.assertEqual(status, 401)
        self.assertEqual(rejected, {"error": "unauthorized"})

        status, accepted = self.mcp_call(
            "tools/call",
            {
                "name": "submit_owner_command",
                "arguments": {
                    "task_node_id": "node-1",
                    "command": "inspect",
                    "idempotency_key": "rejected-key",
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertFalse(self.tool_result(accepted)["duplicate"])

        status, query = self.mcp_call(
            "tools/call",
            {
                "name": "query_execution",
                "arguments": {"execution_id": "does-not-exist"},
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(query["result"]["isError"])
        self.assertEqual(self.tool_result(query)["error"]["code"], "not_found")

    def test_gateway_restart_retains_an_execution_visible_through_mcp(self) -> None:
        status, submitted = self.mcp_call(
            "tools/call",
            {
                "name": "submit_owner_command",
                "arguments": {
                    "task_node_id": "node-1",
                    "command": "inspect",
                    "idempotency_key": "restart-key",
                },
            },
        )
        self.assertEqual(status, 200)
        execution_id = self.tool_result(submitted)["execution_id"]

        self.server.shutdown()
        self.server.server_close()
        self.app.store.close()
        self.app = create_app(
            str(Path(self.temp.name) / "gateway.sqlite3"), "test-token", "local-owner"
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

        status, queried = self.mcp_call(
            "tools/call", {"name": "query_execution", "arguments": {"execution_id": execution_id}}
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.tool_result(queried)["execution_id"], execution_id)

    def wait_for_execution(self, execution_id: str, expected_status: str) -> dict[str, Any]:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            _, response = self.mcp_call(
                "tools/call", {"name": "query_execution", "arguments": {"execution_id": execution_id}}
            )
            execution = self.tool_result(response)
            if execution["execution_status"] == expected_status:
                return execution
            time.sleep(0.02)
        self.fail(f"execution {execution_id} did not reach {expected_status}")

    def submit(self, task_node_id: str, idempotency_key: str) -> str:
        status, response = self.mcp_call(
            "tools/call",
            {
                "name": "submit_owner_command",
                "arguments": {
                    "task_node_id": task_node_id,
                    "command": "inspect",
                    "idempotency_key": idempotency_key,
                },
            },
        )
        self.assertEqual(status, 200)
        return self.tool_result(response)["execution_id"]

    def test_cancel_queued_execution_is_idempotent_through_mcp(self) -> None:
        execution_id = self.submit("node-to-cancel", "cancel-key")
        status, cancelled = self.mcp_call(
            "tools/call", {"name": "cancel_execution", "arguments": {"execution_id": execution_id}}
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            self.tool_result(cancelled),
            {"execution_id": execution_id, "execution_status": "cancelled", "accepted": True},
        )

        _, repeated = self.mcp_call(
            "tools/call", {"name": "cancel_execution", "arguments": {"execution_id": execution_id}}
        )
        self.assertEqual(
            self.tool_result(repeated),
            {"execution_id": execution_id, "execution_status": "cancelled", "accepted": False},
        )

    def test_list_pending_filters_and_sorts_queued_executions(self) -> None:
        later = self.submit("node-b", "list-second")
        first = self.submit("node-a", "list-first")
        status, listed = self.mcp_call("tools/call", {"name": "list_pending", "arguments": {}})
        self.assertEqual(status, 200)
        self.assertEqual([item["execution_id"] for item in self.tool_result(listed)], [later, first])

        _, filtered = self.mcp_call(
            "tools/call", {"name": "list_pending", "arguments": {"task_node_id": "node-a"}}
        )
        self.assertEqual([item["execution_id"] for item in self.tool_result(filtered)], [first])

    def test_review_accepts_a_completed_execution_without_creating_domain_output(self) -> None:
        self.app.enable_test_runtime()
        execution_id = self.submit("node-to-review", "review-key")
        self.wait_for_execution(execution_id, "awaiting_acceptance")
        status, reviewed = self.mcp_call(
            "tools/call",
            {
                "name": "review_execution",
                "arguments": {
                    "execution_id": execution_id,
                    "decision": "accept",
                    "reason": "result is sufficient",
                    "idempotency_key": "review-accept-key",
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            self.tool_result(reviewed),
            {"execution_id": execution_id, "execution_status": "accepted", "duplicate": False},
        )
        _, repeated = self.mcp_call(
            "tools/call",
            {
                "name": "review_execution",
                "arguments": {
                    "execution_id": execution_id,
                    "decision": "reject",
                    "reason": "ignored on retry",
                    "idempotency_key": "review-accept-key",
                },
            },
        )
        self.assertEqual(
            self.tool_result(repeated),
            {"execution_id": execution_id, "execution_status": "accepted", "duplicate": True},
        )

    def test_review_rejection_and_human_takeover_are_terminal(self) -> None:
        for decision, expected_status in (("reject", "rejected"), ("request_human_takeover", "human_takeover")):
            with self.subTest(decision=decision):
                self.app.enable_test_runtime()
                execution_id = self.submit(f"node-{decision}", f"{decision}-command")
                self.wait_for_execution(execution_id, "awaiting_acceptance")
                _, reviewed = self.mcp_call(
                    "tools/call",
                    {"name": "review_execution", "arguments": {
                        "execution_id": execution_id, "decision": decision, "reason": "reviewed",
                        "idempotency_key": f"{decision}-review",
                    }},
                )
                self.assertEqual(self.tool_result(reviewed)["execution_status"], expected_status)

    def test_request_revision_preserves_old_execution_and_creates_successor(self) -> None:
        self.app.enable_test_runtime()
        execution_id = self.submit("node-to-revise", "revision-command")
        original = self.wait_for_execution(execution_id, "awaiting_acceptance")
        _, reviewed = self.mcp_call(
            "tools/call",
            {"name": "review_execution", "arguments": {
                "execution_id": execution_id, "decision": "request_revision", "reason": "add evidence",
                "idempotency_key": "request-revision-key",
            }},
        )
        result = self.tool_result(reviewed)
        self.assertEqual(result["execution_status"], "needs_revision")
        successor_id = result["successor_execution_id"]
        _, old_query = self.mcp_call(
            "tools/call", {"name": "query_execution", "arguments": {"execution_id": execution_id}}
        )
        self.assertEqual(self.tool_result(old_query)["execution_status"], "needs_revision")
        successor = self.wait_for_execution(successor_id, "awaiting_acceptance")
        self.assertEqual(successor["revision_of"], original["execution_id"])
        self.assertEqual(successor["session_id"], original["session_id"])

        self.app.enable_test_runtime(duration_seconds=0.2)
        first = self.submit("shared-node", "first")
        self.wait_for_execution(first, "running")
        second = self.submit("shared-node", "second")
        time.sleep(0.05)
        _, response = self.mcp_call(
            "tools/call", {"name": "query_execution", "arguments": {"execution_id": second}}
        )
        self.assertEqual(self.tool_result(response)["execution_status"], "queued")
        self.wait_for_execution(first, "awaiting_acceptance")
        self.wait_for_execution(second, "awaiting_acceptance")

    def test_review_rejects_invalid_state_with_stable_error(self) -> None:
        execution_id = self.submit("node-not-ready", "not-ready-command")
        _, response = self.mcp_call(
            "tools/call",
            {"name": "review_execution", "arguments": {
                "execution_id": execution_id, "decision": "accept", "reason": "premature",
                "idempotency_key": "not-ready-review",
            }},
        )
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(self.tool_result(response)["error"]["code"], "invalid_state")

    def test_same_task_node_waits_for_existing_worker_lease(self) -> None:
        self.app.enable_test_runtime(duration_seconds=0.2)
        first = self.submit("shared-node", "first")
        self.wait_for_execution(first, "running")
        second = self.submit("shared-node", "second")
        time.sleep(0.05)
        _, response = self.mcp_call(
            "tools/call", {"name": "query_execution", "arguments": {"execution_id": second}}
        )
        self.assertEqual(self.tool_result(response)["execution_status"], "queued")
        self.wait_for_execution(first, "awaiting_acceptance")
        self.wait_for_execution(second, "awaiting_acceptance")

    def test_waiting_answer_creates_a_resume_execution_with_same_session(self) -> None:
        self.app.enable_test_runtime("waiting")
        waiting_id = self.submit("node-to-resume", "waiting-command")
        waiting = self.wait_for_execution(waiting_id, "waiting")
        self.assertEqual(waiting["pending_question"], "test runtime needs an answer")

        self.app.enable_test_runtime()
        _, answered = self.mcp_call(
            "tools/call",
            {"name": "submit_owner_command", "arguments": {
                "task_node_id": "node-to-resume", "command": "the answer is 42",
                "idempotency_key": "answer-command", "execution_id": waiting_id,
            }},
        )
        resumed_id = self.tool_result(answered)["execution_id"]
        resumed = self.wait_for_execution(resumed_id, "awaiting_acceptance")
        self.assertEqual(resumed["resume_of"], waiting_id)
        self.assertEqual(resumed["session_id"], waiting["session_id"])
        self.assertEqual(resumed["result_summary"], "test runtime resumed")

    def test_different_task_nodes_receive_independent_worker_leases(self) -> None:
        self.app.enable_test_runtime(duration_seconds=0.2)
        first = self.submit("node-one", "node-one-key")
        second = self.submit("node-two", "node-two-key")
        self.wait_for_execution(first, "running")
        self.wait_for_execution(second, "running")
        self.wait_for_execution(first, "awaiting_acceptance")
        self.wait_for_execution(second, "awaiting_acceptance")

    def test_fast_agent_passthrough_runtime_completes_without_provider_credentials(self) -> None:
        self.app.enable_fast_agent_passthrough_runtime(str(Path(self.temp.name) / "worker-home"))
        execution_id = self.submit("fast-agent-node", "fast-agent-command")
        execution = self.wait_for_execution(execution_id, "awaiting_acceptance")
        self.assertEqual(execution["result_summary"], "fast-agent passthrough completed")

    def test_fast_agent_passthrough_resume_uses_the_persisted_session(self) -> None:
        home = str(Path(self.temp.name) / "worker-home")
        self.app.enable_fast_agent_passthrough_runtime(home)
        first_id = self.submit("fast-agent-resume-node", "fast-agent-first")
        first = self.wait_for_execution(first_id, "awaiting_acceptance")
        self.app.enable_test_runtime("waiting")
        waiting_id = self.submit("fast-agent-resume-node", "fast-agent-waiting")
        self.wait_for_execution(waiting_id, "waiting")
        self.app.enable_fast_agent_passthrough_runtime(home)
        _, response = self.mcp_call(
            "tools/call",
            {"name": "submit_owner_command", "arguments": {
                "task_node_id": "fast-agent-resume-node", "command": "continue",
                "idempotency_key": "fast-agent-resume", "execution_id": waiting_id,
            }},
        )
        resumed = self.wait_for_execution(self.tool_result(response)["execution_id"], "awaiting_acceptance")
        self.assertEqual(first["session_id"], resumed["session_id"])
        self.assertEqual(resumed["result_summary"], "fast-agent passthrough resumed")

    def test_fast_agent_persistent_home_failure_is_observable_through_mcp(self) -> None:
        invalid_home = Path(self.temp.name) / "not-a-directory"
        invalid_home.write_text("occupied", encoding="utf-8")
        self.app.enable_fast_agent_passthrough_runtime(str(invalid_home))
        execution = self.wait_for_execution(
            self.submit("fast-agent-invalid-home", "fast-agent-invalid-home"), "failed"
        )
        self.assertEqual(execution["error_summary"], "runtime_storage_unavailable")

    def test_test_runtime_completes_queued_execution_through_a_short_lived_worker(self) -> None:
        self.app.enable_test_runtime()
        status, submitted = self.mcp_call(
            "tools/call",
            {
                "name": "submit_owner_command",
                "arguments": {
                    "task_node_id": "node-with-worker",
                    "command": "inspect",
                    "idempotency_key": "worker-success",
                },
            },
        )
        self.assertEqual(status, 200)
        execution_id = self.tool_result(submitted)["execution_id"]
        execution = self.wait_for_execution(execution_id, "awaiting_acceptance")
        self.assertEqual(execution["result_summary"], "test runtime completed")
        _, health_response = self.mcp_call("tools/call", {"name": "health", "arguments": {}})
        self.assertEqual(self.tool_result(health_response)["components"]["worker_runtime"], "ready")

    def test_test_runtime_failure_is_observable_through_mcp(self) -> None:
        self.app.enable_test_runtime("runtime_error")
        execution = self.wait_for_execution(self.submit("node-with-failure", "worker-failure"), "failed")
        self.assertEqual(execution["error_summary"], "runtime_error")

    def test_runtime_exception_timeout_and_nonzero_exit_are_failed(self) -> None:
        for outcome in ("exception", "timeout", "nonzero_exit"):
            with self.subTest(outcome=outcome):
                self.app.enable_test_runtime(outcome)
                execution = self.wait_for_execution(
                    self.submit(f"node-{outcome}", f"worker-{outcome}"), "failed"
                )
                self.assertEqual(execution["error_summary"], outcome)

    def test_runtime_cancel_is_observable_through_mcp(self) -> None:
        self.app.enable_test_runtime("cancelled")
        execution = self.wait_for_execution(
            self.submit("node-with-cancel", "worker-cancel"), "cancelled"
        )
        self.assertEqual(execution["error_summary"], "cancelled")

    def test_authenticated_health_reports_component_states(self) -> None:
        status, response = self.mcp_call("tools/call", {"name": "health", "arguments": {}})
        self.assertEqual(status, 200)
        health = self.tool_result(response)
        self.assertEqual(health["gateway_api_version"], "v1")
        self.assertEqual(health["status"], "ready")
        self.assertEqual(health["components"]["storage"], "ready")


if __name__ == "__main__":
    unittest.main()
