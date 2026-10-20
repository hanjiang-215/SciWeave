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

    def test_different_task_nodes_receive_independent_worker_leases(self) -> None:
        self.app.enable_test_runtime(duration_seconds=0.2)
        first = self.submit("node-one", "node-one-key")
        second = self.submit("node-two", "node-two-key")
        self.wait_for_execution(first, "running")
        self.wait_for_execution(second, "running")
        self.wait_for_execution(first, "awaiting_acceptance")
        self.wait_for_execution(second, "awaiting_acceptance")

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
