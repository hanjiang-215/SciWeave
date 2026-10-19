from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from gateway.app import create_app, make_handler


class GatewayHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(str(Path(self.temp.name) / "gateway.sqlite3"), "test-token")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.app.store.close()
        self.temp.cleanup()

    def request(self, method: str, path: str, body: dict | None = None, token: str = "test-token"):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Authorization", f"Bearer {token}")
        if data:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_health_and_command_query_create_persisted_records(self) -> None:
        status, health = self.request("GET", "/health", token="")
        self.assertEqual((status, health["status"]), (200, "ready"))
        status, created = self.request("POST", "/v1/commands", {"task_node_id": "node-1", "command": "inspect", "idempotency_key": "idem-1"})
        self.assertEqual(status, 202)
        self.assertEqual(created["execution_status"], "created")
        status, execution = self.request("GET", f"/v1/executions/{created['execution_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(execution["session_id"], created["session_id"])
        self.assertEqual(execution["command_status"], "accepted")

    def test_rejects_missing_or_invalid_token(self) -> None:
        status, _ = self.request("POST", "/v1/commands", {}, token="")
        self.assertEqual(status, 401)
        status, _ = self.request("POST", "/v1/commands", {}, token="wrong")
        self.assertEqual(status, 401)

    def test_repeated_idempotency_key_returns_same_execution(self) -> None:
        body = {"task_node_id": "node-1", "command": "inspect", "idempotency_key": "idem-1"}
        _, first = self.request("POST", "/v1/commands", body)
        status, second = self.request("POST", "/v1/commands", body)
        self.assertEqual(status, 200)
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["execution_id"], first["execution_id"])
        self.assertEqual(second["execution_status"], "created")


if __name__ == "__main__":
    unittest.main()
