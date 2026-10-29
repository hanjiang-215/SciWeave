"""B3 / ai4-0hdz: the first formal Wiki revision can be created through a guarded
tool, after which candidates can be submitted."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from llm_wiki.bootstrap import WikiBootstrapService
from llm_wiki.management import WikiManagementService
from llm_wiki.sqlite_store import SqliteStore

DOMAIN = "wiki-fresh"


class _ConfirmedSnapshot:
    status = "confirmed"
    store_id = "wiki-store"
    branch_id = "main"
    commit_hash = "bootstrap-commit"
    reason_code = None


class _FailedSnapshot:
    status = "failed"
    reason_code = "formal_store_not_configured"


class FakeTerminus:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot or _ConfirmedSnapshot()
        self.calls = []

    def ensure_default_formal_snapshot(self, domain_id):
        self.calls.append(domain_id)
        return self.snapshot


class _FormalQuery:
    def get_current(self, domain_id):  # pragma: no cover - not used here
        raise AssertionError


class _CandidateService:
    pass


def _service(tmp: Path, terminus, capabilities):
    store = SqliteStore(str(tmp / "wiki.sqlite"))
    store.initialize()
    bootstrap = WikiBootstrapService(sqlite_store=store, terminus_store=terminus)
    management = WikiManagementService(
        formal_query=_FormalQuery(),
        candidate_service=_CandidateService(),
        caller_capabilities=capabilities,
        sqlite_store=store,
        bootstrap_service=bootstrap,
    )
    return store, management


class BootstrapServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_the_first_formal_revision(self):
        terminus = FakeTerminus()
        store, _ = _service(self.root, terminus, {})
        result = WikiBootstrapService(sqlite_store=store, terminus_store=terminus).bootstrap(DOMAIN)
        self.assertEqual(result.status, "created")
        self.assertIsNotNone(result.formal_revision_id)
        self.assertEqual(store.get_current_formal_revision_id(DOMAIN), result.formal_revision_id)

    def test_is_idempotent(self):
        terminus = FakeTerminus()
        store, _ = _service(self.root, terminus, {})
        service = WikiBootstrapService(sqlite_store=store, terminus_store=terminus)
        first = service.bootstrap(DOMAIN)
        second = service.bootstrap(DOMAIN)
        self.assertEqual(first.formal_revision_id, second.formal_revision_id)
        self.assertEqual(second.status, "already_exists")
        # The second call must not ask TerminusDB for another snapshot.
        self.assertEqual(len(terminus.calls), 1)

    def test_failed_snapshot_is_reported_not_swallowed(self):
        terminus = FakeTerminus(_FailedSnapshot())
        store, _ = _service(self.root, terminus, {})
        result = WikiBootstrapService(sqlite_store=store, terminus_store=terminus).bootstrap(DOMAIN)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.reason_code, "formal_store_not_configured")
        self.assertIsNone(store.get_current_formal_revision_id(DOMAIN))

    def test_missing_domain_is_rejected(self):
        terminus = FakeTerminus()
        store, _ = _service(self.root, terminus, {})
        result = WikiBootstrapService(sqlite_store=store, terminus_store=terminus).bootstrap("")
        self.assertEqual((result.status, result.reason_code), ("failed", "wiki_domain_id_required"))


class BootstrapToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_owner_can_bootstrap_and_role_is_enforced(self):
        terminus = FakeTerminus()
        store, management = _service(
            self.root, terminus, {"owner": frozenset({"formalize"}), "researcher": frozenset({"read"})}
        )
        denied = management.call_tool("bootstrap_wiki", {"wiki_domain_id": DOMAIN}, actor_id="researcher")
        self.assertEqual(denied.status, "denied")

        ok = management.call_tool("bootstrap_wiki", {"wiki_domain_id": DOMAIN}, actor_id="owner")
        self.assertEqual(ok.status, "ok")
        self.assertEqual(ok.result["status"], "created")
        self.assertIsNotNone(store.get_current_formal_revision_id(DOMAIN))

    def test_tool_is_advertised(self):
        names = {definition["name"] for definition in __import__("llm_wiki.management", fromlist=["TOOL_DEFINITIONS"]).TOOL_DEFINITIONS}
        self.assertIn("bootstrap_wiki", names)


if __name__ == "__main__":
    unittest.main()


class HealthReportTests(unittest.TestCase):
    """B12 / ai4-jmiv: the /health provider flags a config/data domain mismatch."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SqliteStore(str(Path(self.tmp.name) / "wiki.sqlite"))
        self.store.initialize()

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_store_reports_no_pointer_but_not_degraded(self):
        from main import _health_report

        report = _health_report(self.store, "configured")()
        self.assertNotEqual(report.get("status"), "degraded")
        self.assertFalse(report["formal_pointer_present"])

    def test_mismatch_reports_degraded_with_known_domains(self):
        from main import _health_report

        self.store.ensure_initial_formal_revision(
            formal_revision_id="r1", result_id="res1", wiki_domain_id="other-domain",
            terminus_store_id="s", formal_branch_id="main", formal_commit_hash="c",
        )
        report = _health_report(self.store, "configured")()
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["reason_code"], "wiki_domain_mismatch")
        self.assertIn("other-domain", report["known_domains"])

    def test_matching_domain_is_healthy(self):
        from main import _health_report

        self.store.ensure_initial_formal_revision(
            formal_revision_id="r2", result_id="res2", wiki_domain_id="configured",
            terminus_store_id="s", formal_branch_id="main", formal_commit_hash="c",
        )
        report = _health_report(self.store, "configured")()
        self.assertNotEqual(report.get("status"), "degraded")
        self.assertTrue(report["formal_pointer_present"])
