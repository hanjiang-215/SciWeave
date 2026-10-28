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
