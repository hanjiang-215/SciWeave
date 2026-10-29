from __future__ import annotations

import json
import threading
import unittest
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from research_mapping.dashboard_source import build_mapping_fragment, create_mapping_dashboard_server


class MappingDashboardSourceTests(unittest.TestCase):
    def test_projects_tasks_and_dependencies_are_projected_from_formal_documents(self) -> None:
        result = SimpleNamespace(
            status="available",
            mapping_domain_id="mapping-1",
            formal_revision_id="formal-7",
            documents=(
                {"@id": "TaskNode/a-v1", "@type": "TaskNode", "logical_id": "a", "version_id": "a-v1", "title": "Prepare data", "task_owner_id": "owner", "execution_status": "succeeded", "lifecycle_state": "formal"},
                {"@id": "TaskNode/b-v1", "@type": "TaskNode", "logical_id": "b", "version_id": "b-v1", "title": "Train model", "task_owner_id": "owner", "execution_status": "waiting", "lifecycle_state": "formal"},
                {"@id": "DependencyEdge/e1", "@type": "DependencyEdge", "source_node_version_ref": {"version_id": "a-v1"}, "target_node_version_ref": {"version_id": "b-v1"}},
            ),
        )
        payload = build_mapping_fragment(result, observed_at="2026-10-22T09:00:00Z")
        self.assertEqual(payload["sourceStatus"], "fresh")
        self.assertEqual(payload["projects"][0]["completed"], 1)
        self.assertEqual(payload["tasks"][0]["status"], "succeeded")
        self.assertEqual(payload["tasks"][1]["prerequisiteIds"], ["a-v1"])
        self.assertEqual(payload["tasks"][1]["status"], "waiting")
        # ai4-fnzt: the projection exposes a stable logical id separately from the
        # immutable version id, so the UI labels the logical task, not "v1".
        self.assertEqual(payload["tasks"][0]["id"], "a-v1")
        self.assertEqual(payload["tasks"][0]["logicalId"], "a")
        self.assertEqual(payload["tasks"][1]["logicalId"], "b")

    def test_unavailable_formal_query_does_not_expose_candidate_documents(self) -> None:
        result = SimpleNamespace(status="inconsistent", mapping_domain_id="mapping-1", documents=({"secret": "candidate"},))
        payload = build_mapping_fragment(result, observed_at="2026-10-22T09:00:00Z")
        self.assertEqual(payload["sourceStatus"], "unavailable")
        self.assertEqual(payload["tasks"], [])
        self.assertNotIn("candidate", json.dumps(payload))

    def test_http_source_is_read_only_and_can_require_bearer_token(self) -> None:
        result = SimpleNamespace(status="available", mapping_domain_id="mapping-1", formal_revision_id="r1", documents=())
        server = create_mapping_dashboard_server(lambda: result, host="127.0.0.1", port=0, token="read-only-token")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with self.assertRaises(HTTPError) as raised:
                urlopen(f"{base}/api/dashboard/source/mapping")
            self.assertEqual(raised.exception.code, 401)
            request = Request(f"{base}/api/dashboard/source/mapping", headers={"Authorization": "Bearer read-only-token"})
            with urlopen(request) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read())["sourceStatus"], "fresh")
            with self.assertRaises(HTTPError) as raised:
                urlopen(Request(f"{base}/api/dashboard/source/mapping", data=b"{}", method="POST"))
            self.assertEqual(raised.exception.code, 405)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()


class ExecutionStatusResolverTests(unittest.TestCase):
    """B7: task status is derived from execution facts when the node has none."""

    def _make_db(self, rows):
        import sqlite3, tempfile
        path = tempfile.mktemp(suffix=".sqlite3")
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE execution_records (task_node_id TEXT, business_key TEXT, mapping_domain_id TEXT, status TEXT)"
        )
        conn.executemany("INSERT INTO execution_records VALUES (?,?,?,?)", rows)
        conn.commit()
        conn.close()
        return path

    def test_status_derived_from_execution_fact(self) -> None:
        from research_mapping.dashboard_source import ExecutionStatusResolver
        path = self._make_db([("a", "a:a-v1:rev-1", "mapping-1", "completed")])
        resolver = ExecutionStatusResolver(path)
        result = SimpleNamespace(
            status="available",
            mapping_domain_id="mapping-1",
            formal_revision_id="formal-7",
            documents=(
                {"@id": "TaskNode/a-v1", "@type": "TaskNode", "logical_id": "a", "version_id": "a-v1", "title": "Prep"},
            ),
        )
        payload = build_mapping_fragment(result, observed_at="2026-10-29T00:00:00Z", execution_status_resolver=resolver)
        self.assertEqual(payload["tasks"][0]["status"], "succeeded")
        self.assertEqual(payload["projects"][0]["completed"], 1)

    def test_without_resolver_stays_unknown(self) -> None:
        result = SimpleNamespace(
            status="available",
            mapping_domain_id="mapping-1",
            formal_revision_id="formal-7",
            documents=(
                {"@id": "TaskNode/a-v1", "@type": "TaskNode", "logical_id": "a", "version_id": "a-v1", "title": "Prep"},
            ),
        )
        payload = build_mapping_fragment(result, observed_at="2026-10-29T00:00:00Z")
        self.assertEqual(payload["tasks"][0]["status"], "unknown")
