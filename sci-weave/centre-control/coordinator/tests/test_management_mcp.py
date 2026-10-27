"""MCP entry for root task dispatch (ai4-nzmm).

Root nodes are never auto-dispatched on a formal-revision event, so without an
MCP entry ``dispatch_root_task`` was only reachable from Python and a task graph
could not be started at all.
"""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from coordinator.management_mcp import create_coordinator_mcp_server, start_in_background


class _RecordingService:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.calls: list[tuple[str, str, str, str]] = []

    def dispatch_root_task(
        self, mapping_domain_id, task_node_id, target_node_version_ref, *, trigger_revision_id
    ) -> bool:
        self.calls.append((mapping_domain_id, task_node_id, target_node_version_ref, trigger_revision_id))
        return self.accepted


class CoordinatorMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _RecordingService()
        self.server = create_coordinator_mcp_server("127.0.0.1", 0, self.service, "test-token")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _post(self, payload, token: str | None = "test-token"):
        request = urllib.request.Request(
            self.base + "/mcp", data=json.dumps(payload).encode(), method="POST"
        )
        request.add_header("Content-Type", "application/json")
        if token is not None:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"null")

    def _call(self, arguments, token: str | None = "test-token"):
        return self._post(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/call",
                "params": {"name": "dispatch_root_task", "arguments": arguments},
            },
            token,
        )

    def test_health_is_reachable_without_a_token(self) -> None:
        with urllib.request.urlopen(self.base + "/health") as response:
            self.assertEqual(json.loads(response.read())["status"], "ready")

    def test_unknown_token_is_rejected(self) -> None:
        status, _ = self._call({"mapping_domain_id": "d"}, token="wrong")
        self.assertEqual(status, 401)

    def test_missing_token_is_rejected(self) -> None:
        status, _ = self._call({"mapping_domain_id": "d"}, token=None)
        self.assertEqual(status, 401)

    def test_the_only_tool_is_dispatch_root_task(self) -> None:
        status, body = self._post({"jsonrpc": "2.0", "id": "1", "method": "tools/list"})
        self.assertEqual(status, 200)
        self.assertEqual([tool["name"] for tool in body["result"]["tools"]], ["dispatch_root_task"])

    def test_dispatch_reaches_the_service(self) -> None:
        status, body = self._call(
            {
                "mapping_domain_id": "iris",
                "task_node_id": "node-root",
                "target_node_version_ref": "node-v1",
                "trigger_revision_id": "rev-1",
            }
        )

        self.assertEqual(status, 200)
        payload = json.loads(body["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "dispatched")
        self.assertTrue(payload["accepted"])
        self.assertEqual(
            self.service.calls, [("iris", "node-root", "node-v1", "rev-1")]
        )

    def test_a_refused_dispatch_is_reported_not_raised(self) -> None:
        self.service.accepted = False

        status, body = self._call(
            {
                "mapping_domain_id": "iris",
                "task_node_id": "node-root",
                "target_node_version_ref": "node-v1",
                "trigger_revision_id": "rev-1",
            }
        )

        self.assertEqual(status, 200)
        payload = json.loads(body["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "not_dispatched")
        self.assertFalse(payload["accepted"])

    def test_incomplete_arguments_are_rejected(self) -> None:
        status, body = self._call({"mapping_domain_id": "iris"})

        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], -32602)
        self.assertEqual(self.service.calls, [])

    def test_an_unknown_tool_is_rejected(self) -> None:
        status, body = self._post(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/call",
                "params": {"name": "delete_everything", "arguments": {}},
            }
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], -32602)

    def test_a_service_failure_is_reported_as_failed(self) -> None:
        class _Broken(_RecordingService):
            def dispatch_root_task(self, *args, **kwargs):
                raise RuntimeError("snapshot unavailable")

        server = create_coordinator_mcp_server("127.0.0.1", 0, _Broken(), "test-token")
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/mcp",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/call",
                    "params": {
                        "name": "dispatch_root_task",
                        "arguments": {
                            "mapping_domain_id": "iris",
                            "task_node_id": "node-root",
                            "target_node_version_ref": "node-v1",
                            "trigger_revision_id": "rev-1",
                        },
                    },
                }
            ).encode(),
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        request.add_header("Authorization", "Bearer test-token")
        with urllib.request.urlopen(request) as response:
            body = json.loads(response.read())

        payload = json.loads(body["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "failed")
        self.assertFalse(payload["accepted"])


if __name__ == "__main__":
    unittest.main()
