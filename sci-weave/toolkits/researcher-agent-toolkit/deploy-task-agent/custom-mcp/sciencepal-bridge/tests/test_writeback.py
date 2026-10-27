from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sciencepal_bridge.report import build_execution_report
from sciencepal_bridge.writeback import DraftBufferWriteBack, WriteBackError


def _report() -> dict:
    return build_execution_report(
        task_node_id="task:t1",
        execution_id="exec-1",
        status="completed",
        run_id="run-1",
        run_elapsed_s=32.2,
        summary="T1 输入检查通过",
        inputs=[],
        artifacts=[{"name": "result.json", "path": "runs/run-1/result.json", "kind": "data", "sha256": "abc123"}],
        acceptance=[{"criterion": "150 行", "met": True, "evidence": "result.json.row_count"}],
        findings=["输入快照一致"],
        limitations=["只验证输入"],
        route_change={"needed": True, "proposal": {"nodes": [{"id": "n2"}], "edges": [], "rationale": "补一条边"}},
    )


class _Handler(BaseHTTPRequestHandler):
    """Mimics the draft-buffer Streamable HTTP JSON-response contract."""

    drafts: dict[str, dict] = {}
    seen_headers: dict[str, str] = {}
    fail_mode: str | None = None

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        return

    def do_POST(self):  # noqa: N802 - stdlib naming
        handler = type(self)
        handler.seen_headers = {
            "authorization": self.headers.get("Authorization"),
            "content-type": self.headers.get("Content-Type"),
        }
        if handler.fail_mode == "unauthorized":
            self._send(401, {"error": "unauthorized", "message": "unknown bearer token"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        name = (request.get("params") or {}).get("name")
        arguments = dict((request.get("params") or {}).get("arguments") or {})
        if name == "create_draft":
            draft_id = f"draft-{len(handler.drafts) + 1}"
            record = {
                "draft_id": draft_id,
                "namespace": arguments.get("namespace"),
                "kind": arguments.get("kind"),
                "title": arguments.get("title"),
                "payload": arguments.get("payload"),
                "submitted_by": arguments.get("submitted_by"),
                "source_task_node_id": arguments.get("source_task_node_id"),
                "source_execution_record_id": arguments.get("source_execution_record_id"),
                "status": "draft",
            }
            handler.drafts[draft_id] = record
            self._result(record)
            return
        if name == "read_draft":
            record = handler.drafts.get(arguments.get("draft_id"))
            if record is None:
                self._error("draft_not_found", "unknown draft id")
                return
            self._result(record)
            return
        self._error("unknown_tool", f"unknown tool {name}")

    def _result(self, payload: dict) -> None:
        self._send(
            200,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(payload)}],
                    "structuredContent": payload,
                    "isError": False,
                },
            },
        )

    def _error(self, code: str, message: str) -> None:
        self._send(
            200,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"code": code, "message": message})}],
                    "isError": True,
                },
            },
        )

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _StubServer:
    def __init__(self) -> None:
        _Handler.drafts = {}
        _Handler.fail_mode = None
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/mcp"

    def set_fail_mode(self, mode: str | None) -> None:
        _Handler.fail_mode = mode

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


class WriteBackTests(unittest.TestCase):
    """ai4-roow: report writes into the draft buffer under the mapping_change kind."""

    def setUp(self) -> None:
        self.server = _StubServer()
        self.addCleanup(self.server.close)
        self.client = DraftBufferWriteBack(self.server.url, "buffer-token", 5)

    def test_create_draft_uses_mapping_change_and_round_trips_payload(self) -> None:
        outcome = self.client.create_draft(
            report=_report(), submitted_by="ai-researcher", idempotency_key="exec-1-key"
        )

        self.assertEqual(outcome["kind"], "mapping_change")
        self.assertEqual(outcome["namespace"], "mapping")
        self.assertEqual(outcome["source_task_node_id"], "task:t1")
        self.assertEqual(outcome["source_execution_record_id"], "exec-1")
        self.assertEqual(outcome["payload"]["report"]["execution_id"], "exec-1")
        self.assertEqual(outcome["payload"]["report"]["sciencepal"]["run_id"], "run-1")
        self.assertEqual(outcome["payload"]["proposed_change_set"]["execution_id"], "exec-1")
        self.assertEqual([node["id"] for node in outcome["payload"]["proposed_change_set"]["nodes"]], ["n2"])

    def test_read_draft_returns_the_stored_payload(self) -> None:
        created = self.client.create_draft(
            report=_report(), submitted_by="ai-researcher", idempotency_key="exec-1-key"
        )
        read_back = self.client.read_draft(created["draft_id"])
        self.assertEqual(read_back["draft_id"], created["draft_id"])
        self.assertEqual(read_back["payload"]["report"]["artifacts"][0]["sha256"], "abc123")

    def test_result_carries_audit_correlation_ids(self) -> None:
        outcome = self.client.create_draft(
            report=_report(), submitted_by="ai-researcher", idempotency_key="exec-1-key"
        )
        self.assertEqual(outcome["execution_id"], "exec-1")
        self.assertEqual(outcome["run_id"], "run-1")
        self.assertEqual(outcome["task_node_id"], "task:t1")
        self.assertTrue(outcome["draft_id"])

    def test_bearer_token_and_json_content_type_are_sent(self) -> None:
        self.client.create_draft(report=_report(), submitted_by="ai-researcher", idempotency_key="k1")
        self.assertEqual(_Handler.seen_headers.get("authorization"), "Bearer buffer-token")
        self.assertIn("application/json", _Handler.seen_headers.get("content-type", ""))

    def test_unauthorized_token_is_denied(self) -> None:
        self.server.set_fail_mode("unauthorized")
        with self.assertRaises(WriteBackError) as caught:
            self.client.create_draft(report=_report(), submitted_by="ai-researcher", idempotency_key="k1")
        self.assertEqual(caught.exception.code, "draft_buffer_denied")

    def test_unknown_draft_read_is_a_stable_error(self) -> None:
        with self.assertRaises(WriteBackError) as caught:
            self.client.read_draft("missing-draft")
        self.assertEqual(caught.exception.code, "draft_not_found")

    def test_unreachable_buffer_is_unavailable(self) -> None:
        client = DraftBufferWriteBack("http://127.0.0.1:1/mcp", "buffer-token", 1)
        with self.assertRaises(WriteBackError) as caught:
            client.create_draft(report=_report(), submitted_by="ai-researcher", idempotency_key="k1")
        self.assertEqual(caught.exception.code, "draft_buffer_unavailable")

    def test_missing_token_fails_before_any_request(self) -> None:
        with self.assertRaises(WriteBackError) as caught:
            DraftBufferWriteBack(self.server.url, "", 1)
        self.assertEqual(caught.exception.code, "draft_buffer_token_missing")


if __name__ == "__main__":
    unittest.main()
