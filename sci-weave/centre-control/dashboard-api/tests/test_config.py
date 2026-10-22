import unittest

from dashboard_api.config import DashboardConfig, ConfigurationError


class DashboardConfigTests(unittest.TestCase):
    def test_reads_listen_address_sources_and_timeout_from_environment(self) -> None:
        config = DashboardConfig.from_environment({
            "SCIWEAVE_DASHBOARD_HOST": "127.0.0.1",
            "SCIWEAVE_DASHBOARD_PORT": "0",
            "SCIWEAVE_DASHBOARD_SOURCE_MAPPING_URL": "http://mapping.internal/read",
            "SCIWEAVE_DASHBOARD_SOURCE_WIKI_URL": "https://wiki.internal/read",
            "SCIWEAVE_DASHBOARD_SOURCE_TIMEOUT_SECONDS": "2.5",
        })
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 0)
        self.assertEqual(config.timeout_seconds, 2.5)
        self.assertEqual(config.source_urls["mapping"], "http://mapping.internal/read")
        self.assertEqual(config.source_urls["wiki"], "https://wiki.internal/read")
        self.assertIsNone(config.source_urls["gateway"])

    def test_rejects_missing_host_and_invalid_port(self) -> None:
        with self.assertRaises(ConfigurationError):
            DashboardConfig.from_environment({"SCIWEAVE_DASHBOARD_PORT": "0"})
        with self.assertRaises(ConfigurationError):
            DashboardConfig.from_environment({"SCIWEAVE_DASHBOARD_HOST": "127.0.0.1", "SCIWEAVE_DASHBOARD_PORT": "70000"})

    def test_rejects_source_urls_with_credentials(self) -> None:
        with self.assertRaises(ConfigurationError):
            DashboardConfig.from_environment({
                "SCIWEAVE_DASHBOARD_HOST": "127.0.0.1",
                "SCIWEAVE_DASHBOARD_PORT": "0",
                "SCIWEAVE_DASHBOARD_SOURCE_MAPPING_URL": "https://user:secret@mapping.internal/read",
            })


if __name__ == "__main__":
    unittest.main()
