import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError

from dashboard_api.sources import SourceSpec, SourceUnavailable, fetch_json


class _FixtureHandler(BaseHTTPRequestHandler):
    payload = b'{"observedAt":"2026-10-22T09:00:00Z"}'
    content_type = "application/json"
    status_code = 200
    authorization = None

    def do_GET(self) -> None:  # noqa: N802
        type(self).authorization = self.headers.get("Authorization")
        self.send_response(self.status_code)
        self.send_header("Content-Type", self.content_type)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, format: str, *args: object) -> None:
        return


class SourceReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.source = SourceSpec("mapping", "Research Mapping", f"http://127.0.0.1:{self.server.server_address[1]}/snapshot", ("projects",))

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_reads_json_from_configured_source(self) -> None:
        _FixtureHandler.payload = json.dumps({"observedAt": "2026-10-22T09:00:00Z", "projects": []}).encode()
        _FixtureHandler.content_type = "application/json; charset=utf-8"
        result = fetch_json(self.source, timeout_seconds=1, max_payload_bytes=1024)
        self.assertEqual(result["observedAt"], "2026-10-22T09:00:00Z")

    def test_sends_source_token_only_to_the_source_service(self) -> None:
        _FixtureHandler.payload = json.dumps({"observedAt": "2026-10-22T09:00:00Z", "projects": []}).encode()
        _FixtureHandler.content_type = "application/json"
        source = SourceSpec(self.source.id, self.source.label, self.source.url, self.source.collections, "source-read-only-token")
        fetch_json(source, timeout_seconds=1, max_payload_bytes=1024)
        self.assertEqual(_FixtureHandler.authorization, "Bearer source-read-only-token")

    def test_rejects_non_json_content_type_and_oversized_payload(self) -> None:
        _FixtureHandler.payload = b"<html>private details</html>"
        _FixtureHandler.content_type = "text/html"
        with self.assertRaises(SourceUnavailable) as raised:
            fetch_json(self.source, timeout_seconds=1, max_payload_bytes=1024)
        self.assertEqual(raised.exception.reason_code, "source_invalid_response")

        _FixtureHandler.payload = b"x" * 2048
        _FixtureHandler.content_type = "application/json"
        with self.assertRaises(SourceUnavailable) as raised:
            fetch_json(self.source, timeout_seconds=1, max_payload_bytes=1024)
        self.assertEqual(raised.exception.reason_code, "source_invalid_response")


class RedirectRejectionTests(unittest.TestCase):
    """ai4-72pa: a source must not be able to bounce the request elsewhere."""

    def setUp(self) -> None:
        self.seen: list[str | None] = []

        class _Target(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                self.seen.append(self.headers.get("Authorization"))
                body = json.dumps({"observedAt": "2026-10-22T09:00:00Z"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        self.target = ThreadingHTTPServer(("127.0.0.1", 0), _Target)
        threading.Thread(target=self.target.serve_forever, daemon=True).start()
        target_url = f"http://127.0.0.1:{self.target.server_address[1]}/steal"

        class _Redirect(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                self.send_response(302)
                self.send_header("Location", target_url)
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                return

        self.redirect = ThreadingHTTPServer(("127.0.0.1", 0), _Redirect)
        threading.Thread(target=self.redirect.serve_forever, daemon=True).start()
        self.source = SourceSpec(
            "mapping", "Research Mapping",
            f"http://127.0.0.1:{self.redirect.server_address[1]}/snapshot",
            ("projects",), "source-read-only-token",
        )

    def tearDown(self) -> None:
        for server in (self.target, self.redirect):
            server.shutdown()
            server.server_close()

    def test_redirect_is_refused_and_the_token_never_reaches_the_target(self) -> None:
        with self.assertRaises(SourceUnavailable) as raised:
            fetch_json(self.source, timeout_seconds=1, max_payload_bytes=1024)
        self.assertEqual(raised.exception.reason_code, "source_redirect_rejected")
        self.assertEqual(self.seen, [])


if __name__ == "__main__":
    unittest.main()