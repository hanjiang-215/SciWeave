from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from llm_wiki.formal_domain import WikiSnapshotRead
from llm_wiki.sqlite_store import SqliteStore
from llm_wiki.terminus_store import TerminusDBWikiCandidateStore


class InitialFormalRevisionTests(unittest.TestCase):
    def test_sqlite_initial_revision_is_idempotent_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteStore(str(Path(directory) / "wiki.db"))
            store.initialize()
            arguments = dict(formal_revision_id="rev", result_id="result", wiki_domain_id="domain",
                             terminus_store_id="store", formal_branch_id="main", formal_commit_hash="commit")
            self.assertEqual(store.ensure_initial_formal_revision(**arguments), "rev")
            self.assertEqual(store.ensure_initial_formal_revision(**arguments), "rev")
            self.assertEqual(store.get_current_formal_revision_id("domain"), "rev")
            self.assertEqual(store.get_succeeded_formalization_result("domain", "rev").formal_commit_hash, "commit")
            with store.connection() as connection:
                connection.execute("CREATE TRIGGER reject_initial_result BEFORE INSERT ON wiki_formalization_result BEGIN SELECT RAISE(ABORT, 'no result'); END")
                connection.commit()
            with self.assertRaises(Exception):
                store.ensure_initial_formal_revision(**{**arguments, "wiki_domain_id": "other"})
            self.assertIsNone(store.get_current_formal_revision_id("other"))
            with store.connection() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM formal_wiki_revision WHERE wiki_domain_id='other'").fetchone()[0], 0)

    def test_sqlite_existing_current_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteStore(str(Path(directory) / "wiki.db"))
            store.initialize()
            with store.connection() as connection:
                connection.execute("INSERT INTO wiki_current_formal_revision VALUES ('domain','existing')")
                connection.commit()
            self.assertEqual(store.ensure_initial_formal_revision(
                formal_revision_id="rev", result_id="result", wiki_domain_id="domain",
                terminus_store_id="store", formal_branch_id="main", formal_commit_hash="commit"), "existing")
            self.assertEqual(store.get_current_formal_revision_id("domain"), "existing")

    def test_terminus_default_snapshot_uses_domain_marker_and_exact_readback(self):
        domain = "domain"
        key = hashlib.sha256(domain.encode()).hexdigest()
        revision = "wiki-default-" + key
        marker = "sciweave-wiki-default-formal:" + key
        documents = [{"@id": "WikiRevision/" + revision, "@type": "WikiRevision", "wiki_revision_id": revision,
                      "title": "", "body_markdown": "", "lifecycle_state": "formal"}]
        requests = []
        head = {"identifier": "commit", "message": marker}
        def opener(url, headers, timeout):
            requests.append(url)
            if "/api/log/" in url:
                return 200, {"content-type": "application/json"}, json.dumps([head]).encode()
            return 200, {"content-type": "application/json", "terminusdb-data-version": "commit:commit"}, json.dumps(documents).encode()
        def request_opener(method, url, headers, body, timeout):
            requests.append(url)
            return opener(url, headers, timeout)
        store = TerminusDBWikiCandidateStore(store_id="store", database="wiki", base_url="http://test", opener=opener, request_opener=request_opener)
        first = store.ensure_default_formal_snapshot(domain)
        second = store.ensure_default_formal_snapshot(domain)
        self.assertEqual((first.status, first.branch_id, first.commit_hash), ("confirmed", "main", "commit"))
        self.assertEqual(first, second)
        self.assertEqual(len(requests), 6)

    def test_terminus_unknown_outcome_fails_closed(self):
        store = TerminusDBWikiCandidateStore(store_id="store", database="wiki", base_url="http://test",
                                            opener=lambda *_: (_ for _ in ()).throw(OSError("offline")))
        self.assertEqual(store.ensure_default_formal_snapshot("domain").status, "unknown")


if __name__ == "__main__":
    unittest.main()


class DomainConsistencyTests(unittest.TestCase):
    """B12: a store whose pointers live under another domain is a mismatch."""

    def test_list_known_domains_reports_pointer_domains(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteStore(str(Path(directory) / "wiki.db"))
            store.initialize()
            store.ensure_initial_formal_revision(
                formal_revision_id="rev", result_id="result", wiki_domain_id="wiki-diabetes",
                terminus_store_id="store", formal_branch_id="main", formal_commit_hash="commit",
            )
            self.assertEqual(store.list_known_domains(), ["wiki-diabetes"])

    def test_domain_mismatch_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteStore(str(Path(directory) / "wiki.db"))
            store.initialize()
            store.ensure_initial_formal_revision(
                formal_revision_id="rev", result_id="result", wiki_domain_id="wiki-diabetes",
                terminus_store_id="store", formal_branch_id="main", formal_commit_hash="commit",
            )
            import importlib.util, sys
            from pathlib import Path as _P
            main_path = _P(__file__).resolve().parents[1] / "src" / "main.py"
            spec = importlib.util.spec_from_file_location("wiki_entry_main", main_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            # configured domain differs from the data domain -> mismatch surfaced
            self.assertTrue(module._warn_if_domain_mismatch(store, "sciweave-wiki"))
            # configured domain matches -> no mismatch
            self.assertFalse(module._warn_if_domain_mismatch(store, "wiki-diabetes"))


class PrereviewBaseKeyTests(unittest.TestCase):
    """ai4-e82q: a moved base must not let an old report pass as current."""

    def test_report_after_base_move_is_a_new_row(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteStore(str(Path(directory) / "wiki.db"))
            store.initialize()
            first = store.append_prereview_report(
                report_id="r1", candidate_id="c1", candidate_head="h1",
                base_formal_revision_id="base-A", rule_set_version="v1",
                checks="{}", verdict="passed", conflict_matrix="{}", created_at="2026-01-01T00:00:00Z",
            )
            self.assertEqual(first["report_id"], "r1")
            # base moved: the same head+rules is re-reviewed against a new base
            second = store.append_prereview_report(
                report_id="r2", candidate_id="c1", candidate_head="h1",
                base_formal_revision_id="base-B", rule_set_version="v1",
                checks="{}", verdict="passed", conflict_matrix="{}", created_at="2026-01-02T00:00:00Z",
            )
            self.assertEqual(second["report_id"], "r2")
            self.assertEqual(second["base_formal_revision_id"], "base-B")
            # current report is the newest one, not the stale base-A row
            current = store.current_prereview_report("c1", "h1")
            self.assertEqual(current["report_id"], "r2")

    def test_current_report_uses_latest_not_arbitrary(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteStore(str(Path(directory) / "wiki.db"))
            store.initialize()
            for i, base in enumerate(("b0", "b1", "b2")):
                store.append_prereview_report(
                    report_id=f"r{i}", candidate_id="c1", candidate_head="h1",
                    base_formal_revision_id=base, rule_set_version="v1",
                    checks="{}", verdict="passed", conflict_matrix="{}",
                    created_at=f"2026-01-0{i+1}T00:00:00Z",
                )
            current = store.current_prereview_report("c1", "h1")
            self.assertEqual(current["report_id"], "r2")


class ContainsReconciliationTests(unittest.TestCase):
    """ai4-hhs4: snapshot reconciliation must compare whole documents, not ids."""

    def test_document_with_same_id_but_altered_body_is_rejected(self):
        from llm_wiki.candidate_submission import _contains

        actual = ({"@id": "WikiRevision/r1", "title": "A", "body_markdown": "tampered"},)
        expected = ({"@id": "WikiRevision/r1", "title": "A", "body_markdown": "original"},)
        self.assertFalse(_contains(actual, expected))

    def test_identical_document_is_accepted(self):
        from llm_wiki.candidate_submission import _contains

        doc = {"@id": "WikiRevision/r1", "title": "A", "body_markdown": "body"}
        self.assertTrue(_contains((dict(doc),), (dict(doc),)))

    def test_missing_null_reference_id_does_not_match_anything(self):
        from llm_wiki.candidate_submission import _contains

        # Both sides carry reference_id=None; the old weak matcher accepted this.
        actual = ({"@type": "ResourceReference", "reference_id": None, "url": "x"},)
        expected = ({"@type": "WikiRevision", "reference_id": None, "title": "A"},)
        self.assertFalse(_contains(actual, expected))
