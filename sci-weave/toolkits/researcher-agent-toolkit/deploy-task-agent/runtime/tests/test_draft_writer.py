import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from work_agent_runtime import BufferMCPDraftWriter, DraftWriteError


class FakeDraftBufferHttp:
    """Minimal in-process ``/mcp`` stub that answers ``create_draft``."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                if body.get("method") == "tools/call":
                    self.server.calls.append(body["params"].get("arguments") or {})
                    text = json.dumps({"draft_id": "draft-http-1"})
                else:
                    text = "{}"
                payload = json.dumps(
                    {"jsonrpc": "2.0", "id": body.get("id"), "result": {"content": [{"type": "text", "text": text}]}}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args) -> None:  # keep test output clean
                pass

        self.calls: list[dict] = []

        class Server(ThreadingHTTPServer):
            def __init__(self) -> None:
                super().__init__(("127.0.0.1", 0), Handler)

        self.server = Server()
        self.server.calls = self.calls


class BufferMCPDraftWriterTests(unittest.TestCase):
    def test_posts_create_draft_and_returns_draft_id(self) -> None:
        buffer = FakeDraftBufferHttp()
        server = buffer.server
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            writer = BufferMCPDraftWriter(
                endpoint=f"http://127.0.0.1:{server.server_port}/mcp",
                token="test-token",
                namespace="mapping",
                submitter_id="agent-1",
            )
            draft_id = writer.write(target_id="node-1", payload="result summary")
            self.assertEqual(draft_id, "draft-http-1")
            self.assertEqual(len(buffer.calls), 1)
            call = buffer.calls[0]
            self.assertEqual(call["namespace"], "mapping")
            self.assertEqual(call["source_task_node_id"], "node-1")
            self.assertEqual(call["submitted_by"], "agent-1")
        finally:
            server.shutdown()
            server.server_close()

    def test_unreachable_endpoint_raises_draft_unavailable(self) -> None:
        writer = BufferMCPDraftWriter(
            endpoint="http://127.0.0.1:1/mcp",
            token="test-token",
            namespace="mapping",
            submitter_id="agent-1",
            timeout_seconds=1.0,
        )
        with self.assertRaises(DraftWriteError) as ctx:
            writer.write(target_id="node-1", payload="x")
        self.assertEqual(str(ctx.exception), "draft_unavailable")

    def test_invalid_response_raises_draft_invalid_response(self) -> None:
        class BrokenHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"not json")

            def log_message(self, *args) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), BrokenHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            writer = BufferMCPDraftWriter(
                endpoint=f"http://127.0.0.1:{server.server_port}/mcp",
                token="test-token",
                namespace="mapping",
                submitter_id="agent-1",
            )
            with self.assertRaises(DraftWriteError) as ctx:
                writer.write(target_id="node-1", payload="x")
            self.assertEqual(str(ctx.exception), "draft_invalid_response")
        finally:
            server.shutdown()
            server.server_close()

    def test_requires_endpoint_and_token(self) -> None:
        with self.assertRaises(ValueError):
            BufferMCPDraftWriter(endpoint="", token="t", namespace="mapping", submitter_id="a")
        with self.assertRaises(ValueError):
            BufferMCPDraftWriter(endpoint="http://x", token="", namespace="mapping", submitter_id="a")


if __name__ == "__main__":
    unittest.main()