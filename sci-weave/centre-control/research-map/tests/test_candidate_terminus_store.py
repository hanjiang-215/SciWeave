from __future__ import annotations

import json
import unittest
from urllib.parse import urlparse

from research_mapping.terminus_store import TerminusDBStore


class CandidateTerminusDBStoreTestCase(unittest.TestCase):
    def test_creates_candidate_from_exact_base_and_confirms_commit(self):
        base_commit = "base-commit"
        candidate_commit = "candidate-commit"
        documents = [{"@type": "TaskNode", "@id": "TaskNode/n1", "logical_id": "n1"}]
        events = []
        write_completed = False

        def request(method, url, headers, body, timeout):
            nonlocal write_completed
            path = urlparse(url).path
            events.append((method, path, headers, body))
            if method == "GET" and path == "/api/db/store/db":
                return 200, {"Content-Type": "application/json"}, json.dumps({"branches": ["main"]}).encode()
            if method == "POST" and "/api/branch/" in path:
                return 200, {"Content-Type": "application/json"}, b'{"api:status":"api:success"}'
            if method == "POST" and "/api/reset/" in path:
                return 200, {"Content-Type": "application/json"}, b'{"api:status":"api:success"}'
            if method == "GET" and "/api/log/" in path:
                return 200, {"Content-Type": "application/json"}, json.dumps([
                    {"identifier": candidate_commit if write_completed else base_commit, "author": "sciweave",
                     "message": _message("idem-1", documents) if write_completed else "base"}
                ]).encode()
            if method == "POST" and "/api/document/" in path:
                write_completed = True
                return 200, {"Content-Type": "application/json", "TerminusDB-Data-Version": f"commit:{candidate_commit}"}, b'["TaskNode/n1"]'
            if method == "GET" and "/api/document/" in path and "/commit/" in path:
                return 200, {"Content-Type": "application/json", "TerminusDB-Data-Version": f"commit:{candidate_commit}"}, json.dumps(documents).encode()
            self.fail(f"unexpected request: {method} {url}")

        store = TerminusDBStore(base_url="http://terminus", username="admin", password="secret", request_opener=request, store_id="store", database="db")

        result = store.create_candidate_snapshot("domain", base_commit, json.dumps(documents), "idem-1")

        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.store_id, "store")
        self.assertEqual(result.branch_id, "candidate-" + _key_suffix("idem-1"))
        self.assertEqual(result.commit_hash, candidate_commit)
        self.assertEqual([event[0] for event in events], ["GET", "POST", "POST", "GET", "POST", "GET", "GET"])
        reset = next(event for event in events if "/api/reset/" in event[1])
        self.assertEqual(json.loads(reset[3]), {"commit_descriptor": f"store/db/local/commit/{base_commit}"})

    def test_reconciles_existing_branch_without_rewriting_candidate(self):
        candidate_commit = "already-written"
        documents = [{"@type": "TaskNode", "@id": "TaskNode/n1", "logical_id": "n1"}]
        events = []

        def request(method, url, headers, body, timeout):
            path = urlparse(url).path
            events.append((method, path))
            if method == "GET" and path == "/api/db/store/db":
                return 200, {"Content-Type": "application/json"}, json.dumps({"branches": ["main", "candidate-" + _key_suffix("idem-1")]}).encode()
            if method == "GET" and "/api/log/" in path:
                return 200, {"Content-Type": "application/json"}, json.dumps([
                    {"identifier": candidate_commit, "author": "sciweave", "message": _message("idem-1", documents)}
                ]).encode()
            if method == "GET" and "/api/document/" in path and "/commit/" in path:
                return 200, {"Content-Type": "application/json", "TerminusDB-Data-Version": f"commit:{candidate_commit}"}, json.dumps(documents).encode()
            self.fail(f"reconciliation must not write: {method} {url}")

        store = TerminusDBStore(base_url="http://terminus", username="admin", password="secret", request_opener=request, store_id="store", database="db")

        result = store.create_candidate_snapshot("domain", "base-commit", json.dumps(documents), "idem-1")

        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.commit_hash, candidate_commit)
        self.assertEqual(len(events), 3)

    def test_existing_branch_with_different_identity_is_unknown_and_not_overwritten(self):
        def request(method, url, headers, body, timeout):
            path = urlparse(url).path
            if method == "GET" and path == "/api/db/store/db":
                return 200, {"Content-Type": "application/json"}, json.dumps({"branches": ["main", "candidate-" + _key_suffix("idem-1")]}).encode()
            if method == "GET" and "/api/log/" in path:
                return 200, {"Content-Type": "application/json"}, b'[{"identifier":"foreign","author":"someone-else","message":"other"}]'
            self.fail("must not write or read unverified candidate content")

        store = TerminusDBStore(base_url="http://terminus", username="admin", password="secret", request_opener=request, store_id="store", database="db")

        result = store.create_candidate_snapshot("domain", "base-commit", '[{"id":"n1"}]', "idem-1")

        self.assertEqual(result.status, "unknown")
        self.assertEqual(result.reason_code, "store_result_unknown")


def _key_suffix(key: str) -> str:
    import hashlib
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _message(key: str, documents) -> str:
    import hashlib
    digest = hashlib.sha256(json.dumps(documents, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    return f"sciweave-candidate:{_key_suffix(key)}:{digest}"


if __name__ == "__main__":
    unittest.main()
