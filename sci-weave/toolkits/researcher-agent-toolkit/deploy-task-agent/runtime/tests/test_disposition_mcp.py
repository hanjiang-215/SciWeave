"""The six disposition tools over the durable store (ai4-58d0)."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from work_agent_runtime import SqliteExecutionStore
from work_agent_runtime.disposition_mcp import create_disposition_server


class DispositionMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SqliteExecutionStore(os.path.join(self._tmp.name, "executions.sqlite3"))
        self.addCleanup(self.store.close)
        self.server = create_disposition_server("127.0.0.1", 0, self.store, "test-token")
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    # -- helpers ------------------------------------------------------------

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

    def _call(self, name: str, arguments: dict | None = None, token: str | None = "test-token"):
        return self._post(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            },
            token,
        )

    def _payload(self, body) -> dict:
        return json.loads(body["result"]["content"][0]["text"])

    def _execution(self, event_id: str = "event-1") -> str:
        return self.store.enqueue("node-1", event_id).execution_id

    # -- surface ------------------------------------------------------------

    def test_all_six_documented_tools_are_exposed(self) -> None:
        status, body = self._post({"jsonrpc": "2.0", "id": "1", "method": "tools/list"})

        self.assertEqual(status, 200)
        self.assertEqual(
            [tool["name"] for tool in body["result"]["tools"]],
            [
                "health",
                "query_execution",
                "list_pending",
                "cancel_execution",
                "answer_question",
                "review_execution",
            ],
        )

    def test_health_reports_ready_without_a_token(self) -> None:
        with urllib.request.urlopen(self.base + "/health") as response:
            self.assertEqual(json.loads(response.read())["status"], "ready")

    def test_an_unknown_token_is_rejected(self) -> None:
        self.assertEqual(self._call("health", token="wrong")[0], 401)
        self.assertEqual(self._call("health", token=None)[0], 401)

    def test_health_counts_pending_executions(self) -> None:
        self._execution()

        status, body = self._call("health")

        self.assertEqual(status, 200)
        self.assertEqual(self._payload(body), {"status": "ready", "pending": 1})

    def test_query_execution_returns_the_record(self) -> None:
        execution_id = self._execution()

        payload = self._payload(self._call("query_execution", {"execution_id": execution_id})[1])

        self.assertEqual(payload["execution_id"], execution_id)
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["reviews"], [])

    def test_query_of_an_unknown_execution_is_not_found(self) -> None:
        payload = self._payload(self._call("query_execution", {"execution_id": "nope"})[1])

        self.assertEqual(payload["status"], "not_found")

    def test_list_pending_hides_finished_work(self) -> None:
        done = self._execution("event-1")
        record = self.store.get(done)
        self.store.start(record)
        self.store.complete(record, "draft-1")
        waiting = self._execution("event-2")

        payload = self._payload(self._call("list_pending")[1])

        self.assertEqual([row["execution_id"] for row in payload["executions"]], [waiting])

    def test_cancel_execution_moves_a_queued_execution(self) -> None:
        execution_id = self._execution()

        payload = self._payload(self._call("cancel_execution", {"execution_id": execution_id})[1])

        self.assertEqual(payload["status"], "cancelled")
        self.assertEqual(self.store.get(execution_id).status, "cancelled")

    def test_cancelling_a_finished_execution_is_an_invalid_transition(self) -> None:
        execution_id = self._execution()
        record = self.store.get(execution_id)
        self.store.start(record)
        self.store.complete(record, "draft-1")

        payload = self._payload(self._call("cancel_execution", {"execution_id": execution_id})[1])

        self.assertEqual(payload["status"], "invalid_transition")
        self.assertEqual(self.store.get(execution_id).status, "completed")

    def test_answer_question_returns_the_execution_to_the_queue(self) -> None:
        execution_id = self._execution()
        question = self.store.ask(execution_id, "which dataset version?")

        payload = self._payload(
            self._call("answer_question", {"question_id": question["question_id"], "answer": "v3"})[1]
        )

        self.assertEqual(payload["status"], "queued")
        self.assertEqual(self.store.get(execution_id).status, "queued")

    def test_an_empty_answer_is_rejected_as_invalid_params(self) -> None:
        execution_id = self._execution()
        question = self.store.ask(execution_id, "which dataset version?")

        status, body = self._call(
            "answer_question", {"question_id": question["question_id"], "answer": "   "}
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], -32602)

    def test_review_execution_records_the_decision(self) -> None:
        execution_id = self._execution()
        record = self.store.get(execution_id)
        self.store.start(record)
        self.store.complete(record, "draft-1")

        payload = self._payload(
            self._call(
                "review_execution",
                {"execution_id": execution_id, "decision": "accepted", "reason": "checked"},
            )[1]
        )

        self.assertEqual(payload["decision"], "accepted")
        self.assertEqual(len(self.store.reviews(execution_id)), 1)

    def test_reviewing_an_unfinished_execution_is_an_invalid_transition(self) -> None:
        execution_id = self._execution()

        payload = self._payload(
            self._call(
                "review_execution",
                {"execution_id": execution_id, "decision": "accepted", "reason": "checked"},
            )[1]
        )

        self.assertEqual(payload["status"], "invalid_transition")

    def test_accepted_review_sets_confirmation_status_locally(self) -> None:
        # B1: with no uplink configured, accepted still records locally and the
        # local audit mirror shows confirmation_status=confirmed.
        execution_id = self._execution()
        record = self.store.get(execution_id)
        self.store.start(record)
        self.store.complete(record, "draft-1")

        payload = self._payload(
            self._call(
                "review_execution",
                {"execution_id": execution_id, "decision": "accepted", "reason": "checked"},
            )[1]
        )

        self.assertEqual(payload["confirmation_status"], "confirmed")
        row = self.store._connection.execute(
            "SELECT confirmation_status FROM execution WHERE execution_id = ?", (execution_id,)
        ).fetchone()
        self.assertEqual(row["confirmation_status"], "confirmed")

    def test_accepted_review_forwards_to_centre_when_uplink_configured(self) -> None:
        # B1: when CONFIRM_UPLINK_URL/TOKEN are set, an accepted review must POST
        # confirm_execution to the centre gateway so the task becomes done there.
        received = {}

        class _FakeHandler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: D401 - silence
                return

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                received["auth"] = self.headers.get("Authorization")
                body = json.loads(self.rfile.read(length))
                received["payload"] = body
                inner = {"execution_id": body["params"]["arguments"]["execution_id"],
                         "decision": body["params"]["arguments"]["decision"],
                         "confirmation_status": "confirmed", "status": "completed"}
                out = {"jsonrpc": "2.0", "id": body.get("id"), "result": {
                    "content": [{"type": "text", "text": json.dumps(inner)}]}}
                data = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        fake = ThreadingHTTPServer(("127.0.0.1", 0), _FakeHandler)
        threading.Thread(target=fake.serve_forever, daemon=True).start()
        self.addCleanup(fake.server_close)
        self.addCleanup(fake.shutdown)
        os.environ["CONFIRM_UPLINK_URL"] = f"http://127.0.0.1:{fake.server_address[1]}/mcp"
        os.environ["CONFIRM_UPLINK_TOKEN"] = "gw-token"
        self.addCleanup(os.environ.pop, "CONFIRM_UPLINK_URL", None)
        self.addCleanup(os.environ.pop, "CONFIRM_UPLINK_TOKEN", None)

        execution_id = self._execution()
        record = self.store.get(execution_id)
        self.store.start(record)
        self.store.complete(record, "draft-1")

        payload = self._payload(
            self._call(
                "review_execution",
                {"execution_id": execution_id, "decision": "accepted", "reason": "checked"},
            )[1]
        )

        self.assertEqual(payload.get("centre_confirmation", {}).get("confirmation_status"), "confirmed")
        self.assertEqual(received["auth"], "Bearer gw-token")
        self.assertEqual(received["payload"]["params"]["name"], "confirm_execution")
        self.assertEqual(received["payload"]["params"]["arguments"]["decision"], "accepted")

    def test_an_unknown_tool_is_rejected(self) -> None:
        status, body = self._call("delete_everything")

        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], -32602)

    def test_missing_arguments_are_rejected(self) -> None:
        status, body = self._call("query_execution", {})

        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
