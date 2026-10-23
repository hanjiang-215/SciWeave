from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request

from draft_buffer import BufferError
from draft_buffer.config import BufferConfig
from draft_buffer.main import dispatch
from draft_buffer.mcp_http import create_mcp_server
from draft_buffer.service import DraftBufferService


class MemoryStore:
    def __init__(self):
        self.documents = []
        self.writes = 0

    def initialize_schema(self):
        return None

    def read_all(self):
        return [dict(item) for item in self.documents]

    def write(self, documents, operation, idempotency_key):
        self.writes += 1
        self.documents = [dict(item) for item in documents]
        return f"commit-{self.writes}"


def _service() -> DraftBufferService:
    return DraftBufferService(MemoryStore(), {"mapping": frozenset({"map-owner"}), "wiki": frozenset({"wiki-owner"})})


class McpHttpTransportTests(unittest.TestCase):
    def setUp(self):
        self.service = _service()
        server = create_mcp_server(
            lambda request: dispatch(self.service, request),
            host="127.0.0.1",
            port=0,
            tokens={"token-researcher": "researcher", "token-wiki-owner": "wiki-owner", "token-map-owner": "map-owner"},
        )
        self.server = server
        self.port = server.server_address[1]
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _post(self, payload, token=None, path="/mcp"):
        body = json.dumps(payload, ensure_ascii=False).encode()
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            try:
                decoded = json.loads(body)
            except json.JSONDecodeError:
                decoded = body
            return error.code, decoded

    def test_health_requires_no_token(self):
        response = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=5)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read().decode("utf-8"))["protocol"], "mcp-streamable-http")

    def test_initialize_and_tools_list_require_a_valid_bearer_token(self):
        status, body = self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}, token=None)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")
        status, body = self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(status, 401)

    def test_unknown_token_is_rejected(self):
        status, body = self._post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token="token-unknown")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")

    def test_initialize_succeeds_with_a_valid_token(self):
        status, body = self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}, token="token-researcher")
        self.assertEqual(status, 200)
        self.assertEqual(body["id"], 1)
        self.assertEqual(body["result"]["serverInfo"]["name"], "sciweave-draft-buffer")

    def test_tool_call_injects_authenticated_actor_over_client_argument(self):
        status, body = self._post(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "create_draft", "arguments": {"namespace": "wiki", "kind": "wiki_document", "title": "Page", "payload": {}, "submitted_by": "someone-else", "idempotency_key": "http-key"}}},
            token="token-researcher",
        )
        self.assertEqual(status, 200)
        result = body["result"]
        self.assertFalse(result["isError"])
        stored = self.service.read_draft(result["structuredContent"]["draft_id"], actor_id="wiki-owner")["draft"]
        # The client-supplied submitted_by must be overwritten by the bearer identity.
        self.assertEqual(stored["submitted_by"], "researcher")

    def test_review_as_the_namespace_owner_is_allowed_through_http(self):
        draft = self.service.create_draft("wiki", "wiki_document", "Page", {}, "researcher", "create-key")
        self.service.submit_draft(draft["draft_id"], "submit-key", actor_id="researcher")
        status, body = self._post(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "review_draft", "arguments": {"draft_id": draft["draft_id"], "decision": "accept", "reason": "reviewed", "idempotency_key": "review-key"}}},
            token="token-wiki-owner",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["structuredContent"]["status"], "accepted")

    def test_wrong_token_cannot_review_other_namespace(self):
        draft = self.service.create_draft("mapping", "mapping_change", "Route", {}, "researcher", "create-key")
        self.service.submit_draft(draft["draft_id"], "submit-key", actor_id="researcher")
        status, body = self._post(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "review_draft", "arguments": {"draft_id": draft["draft_id"], "decision": "accept", "reason": "nope", "idempotency_key": "review-key"}}},
            token="token-wiki-owner",
        )
        self.assertEqual(status, 200)
        result = body["result"]
        self.assertTrue(result["isError"])
        error_payload = json.loads(result["content"][0]["text"])
        self.assertEqual(error_payload["code"], "forbidden")

    def test_non_mcp_path_and_disallowed_methods(self):
        status, body = self._post({}, token="token-researcher", path="/other")
        self.assertEqual(status, 404)
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/mcp", method="DELETE")
        try:
            urllib.request.urlopen(request, timeout=5)
            self.fail("DELETE should not be allowed")
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 405)

    def test_malformed_json_gets_parse_error(self):
        body = b"{not-json"
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/mcp", data=body, headers={"Content-Type": "application/json", "Authorization": "Bearer token-researcher"}, method="POST")
        try:
            urllib.request.urlopen(request, timeout=5)
            self.fail("malformed JSON should be rejected")
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 400)
            decoded = json.loads(error.read().decode("utf-8"))
            self.assertEqual(decoded["error"]["code"], -32700)

    def test_config_requires_host_port_and_tokens_together(self):
        config = BufferConfig.from_environment({
            "SCIWEAVE_BUFFER_TERMINUSDB_URL": "http://127.0.0.1:0",
            "SCIWEAVE_BUFFER_TERMINUSDB_DATABASE": "buffer-test",
            "SCIWEAVE_BUFFER_REVIEWERS_JSON": '{"mapping":["map-owner"],"wiki":["wiki-owner"]}',
            "SCIWEAVE_BUFFER_MCP_HOST": "127.0.0.1",
            "SCIWEAVE_BUFFER_MCP_PORT": "0",
            "SCIWEAVE_BUFFER_MCP_TOKENS_JSON": '{"tok":"researcher"}',
        })
        self.assertEqual(config.mcp_host, "127.0.0.1")
        self.assertEqual(config.tokens, {"tok": "researcher"})
        with self.assertRaises(BufferError):
            BufferConfig.from_environment({
                "SCIWEAVE_BUFFER_TERMINUSDB_URL": "http://127.0.0.1:0",
                "SCIWEAVE_BUFFER_TERMINUSDB_DATABASE": "buffer-test",
                "SCIWEAVE_BUFFER_MCP_HOST": "127.0.0.1",
            })


if __name__ == "__main__":
    unittest.main()