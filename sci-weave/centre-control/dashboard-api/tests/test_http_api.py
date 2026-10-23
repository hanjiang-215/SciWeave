import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dashboard_api.aggregator import DashboardAggregator
from dashboard_api.config import DashboardConfig
from dashboard_api.http_server import create_dashboard_server


class DashboardHttpApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = DashboardConfig.from_environment({
            "SCIWEAVE_DASHBOARD_HOST": "127.0.0.1",
            "SCIWEAVE_DASHBOARD_PORT": "0",
            "SCIWEAVE_DASHBOARD_CORS_ORIGIN": "https://dashboard.example.invalid",
        })
        self.server = create_dashboard_server(self.config, DashboardAggregator(self.config.source_specs, lambda source: {}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_get_snapshot_returns_unavailable_sources_instead_of_server_error(self) -> None:
        with urlopen(f"{self.base_url}/api/dashboard/snapshot") as response:
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["mode"], "live")
            self.assertTrue(payload["partial"])
            self.assertEqual(len(payload["sources"]), 4)
            self.assertEqual(payload["sources"][0]["status"], "unavailable")

    def test_health_endpoint_is_minimal(self) -> None:
        with urlopen(f"{self.base_url}/health") as response:
            payload = json.loads(response.read())
            self.assertEqual(payload, {"status": "ready", "api_version": "v1"})

    def test_write_methods_are_rejected_without_calling_aggregator(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            urlopen(Request(f"{self.base_url}/api/dashboard/snapshot", data=b"{}", method="POST"))
        self.assertEqual(raised.exception.code, 405)
        payload = json.loads(raised.exception.read())
        self.assertEqual(payload["error"], "method_not_allowed")

    def test_preflight_returns_only_the_configured_origin(self) -> None:
        request = Request(f"{self.base_url}/api/dashboard/snapshot", method="OPTIONS", headers={"Origin": "https://dashboard.example.invalid", "Access-Control-Request-Method": "GET"})
        with urlopen(request) as response:
            self.assertEqual(response.status, 204)
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], "https://dashboard.example.invalid")

    def test_preflight_does_not_allow_another_origin(self) -> None:
        request = Request(f"{self.base_url}/api/dashboard/snapshot", method="OPTIONS", headers={"Origin": "https://attacker.example.invalid", "Access-Control-Request-Method": "GET"})
        with urlopen(request) as response:
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))


if __name__ == "__main__":
    unittest.main()
