import unittest
from datetime import datetime, timezone

from dashboard_api.aggregator import DashboardAggregator
from dashboard_api.sources import SourceSpec


SOURCES = (
    SourceSpec("mapping", "Research Mapping", "https://mapping.invalid/snapshot", ("projects", "tasks", "events")),
    SourceSpec("wiki", "LLM-Wiki", "https://wiki.invalid/snapshot", ("wikiDocuments", "wikiCandidates", "events")),
    SourceSpec("gateway", "Gateway", "https://gateway.invalid/snapshot", ("executions", "services", "events")),
    SourceSpec("queue", "消息监听", None, ("services", "events")),
)


class DashboardAggregatorTests(unittest.TestCase):
    def test_merges_configured_sources_and_preserves_source_identity(self) -> None:
        def fetch(source: SourceSpec) -> dict[str, object]:
            if source.id == "mapping":
                return {"observedAt": "2026-10-22T09:00:00Z", "projects": [{"id": "p1"}], "tasks": [{"id": "t1"}], "events": []}
            if source.id == "wiki":
                return {"observedAt": "2026-10-22T09:01:00Z", "wikiDocuments": [{"id": "w1"}], "wikiCandidates": [], "events": []}
            return {"observedAt": "2026-10-22T09:02:00Z", "executions": [{"id": "e1"}], "services": [{"id": "s1"}], "events": []}

        aggregator = DashboardAggregator(SOURCES, fetch, now=lambda: datetime(2026, 10, 22, tzinfo=timezone.utc))
        result = aggregator.get_snapshot()
        self.assertEqual(result["projects"], [{"id": "p1"}])
        self.assertEqual(result["tasks"], [{"id": "t1"}])
        self.assertEqual(result["wikiDocuments"], [{"id": "w1"}])
        self.assertEqual(result["executions"], [{"id": "e1"}])
        self.assertEqual([source["id"] for source in result["sources"]], ["mapping", "wiki", "gateway", "queue"])
        self.assertEqual(result["sources"][0]["observedAt"], "2026-10-22T09:00:00Z")
        self.assertEqual(result["sources"][3]["status"], "unavailable")
        self.assertTrue(result["partial"])

    def test_keeps_successful_data_when_one_source_fails(self) -> None:
        def fetch(source: SourceSpec) -> dict[str, object]:
            if source.id == "wiki":
                raise TimeoutError("token=secret stack=private")
            return {"observedAt": "2026-10-22T09:00:00Z", "projects": [{"id": "p1"}]}

        result = DashboardAggregator(SOURCES, fetch).get_snapshot()
        self.assertEqual(result["projects"], [{"id": "p1"}])
        self.assertEqual(result["sources"][1]["status"], "unavailable")
        self.assertNotIn("secret", str(result))
        self.assertNotIn("private", str(result))
        self.assertTrue(result["partial"])

    def test_invalid_fragment_is_reported_without_discarding_other_sources(self) -> None:
        def fetch(source: SourceSpec) -> dict[str, object]:
            if source.id == "mapping":
                return {"observedAt": "2026-10-22T09:00:00Z", "projects": "not-a-list"}
            return {"observedAt": "2026-10-22T09:01:00Z", "wikiDocuments": [{"id": "w1"}]}

        result = DashboardAggregator(SOURCES, fetch).get_snapshot()
        self.assertEqual(result["sources"][0]["status"], "unavailable")
        self.assertEqual(result["wikiDocuments"], [{"id": "w1"}])

    def test_drops_unapproved_fields_from_source_objects(self) -> None:
        project = {"id": "p1", "name": "路线", "routeId": "r1", "completed": 1, "total": 2, "attentionCount": 0, "accessToken": "do-not-forward"}
        def fetch(source: SourceSpec) -> dict[str, object]:
            if source.id == "mapping":
                return {"observedAt": "2026-10-22T09:00:00Z", "projects": [project]}
            return {"observedAt": "2026-10-22T09:01:00Z"}

        result = DashboardAggregator(SOURCES, fetch).get_snapshot()
        self.assertEqual(result["projects"], [{key: value for key, value in project.items() if key != "accessToken"}])
        self.assertNotIn("do-not-forward", str(result))

    def test_redacts_sensitive_diagnostic_strings(self) -> None:
        service = {"id": "g1", "name": "Gateway", "role": "task-agent", "status": "unavailable", "error": "Authorization: Bearer super-secret at C:\\private\\data"}
        def fetch(source: SourceSpec) -> dict[str, object]:
            return {"observedAt": "2026-10-22T09:00:00Z", "services": [service]}

        result = DashboardAggregator(SOURCES, fetch).get_snapshot()
        serialized = str(result)
        self.assertNotIn("super-secret", serialized)
        self.assertNotIn("C:\\private", serialized)
        self.assertIn("已隐藏", serialized)

    def test_reports_stale_source_as_partial(self) -> None:
        def fetch(source: SourceSpec) -> dict[str, object]:
            return {"observedAt": "2026-10-22T09:00:00Z", "sourceStatus": "stale"}

        result = DashboardAggregator(SOURCES[:1], fetch).get_snapshot()
        self.assertEqual(result["sources"][0]["status"], "stale")
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
