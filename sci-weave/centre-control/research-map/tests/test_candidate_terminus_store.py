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
                self.assertEqual(json.loads(body), {"origin": "store/db/local/branch/main"})
                return 200, {"Content-Type": "application/json"}, b'{"api:status":"api:success"}'
            if method == "POST" and "/api/reset/" in path:
                self.assertEqual(json.loads(body), {"commit_descriptor": f"store/db/local/commit/{base_commit}"})
                return 200, {"Content-Type": "application/json"}, b'{"api:status":"api:success"}'
            if method == "GET" and "/api/log/" in path:
                return 200, {"Content-Type": "application/json"}, json.dumps([
                    {"identifier": candidate_commit if write_completed else base_commit, "author": "sciweave",
                     "message": _message("idem-1", "domain", base_commit, documents) if write_completed else "base"}
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
        self.assertEqual(result.branch_id, "candidate-" + _full_key("idem-1"))
        self.assertEqual(result.commit_hash, candidate_commit)
        self.assertEqual([event[0] for event in events], ["GET", "POST", "POST", "GET", "POST", "GET", "GET"])

    def test_reconciles_existing_exact_candidate_without_rewriting(self):
        candidate_commit = "already-written"
        base_commit = "base-commit"
        documents = [{"@type": "TaskNode", "@id": "TaskNode/n1", "logical_id": "n1"}]
        calls = []
        def request(method, url, headers, body, timeout):
            path = urlparse(url).path
            calls.append((method, path))
            if method == "GET" and path == "/api/db/store/db":
                return 200, {}, json.dumps({"branches": ["candidate-" + _full_key("idem-1")]}).encode()
            if method == "GET" and "/api/log/" in path:
                return 200, {}, json.dumps([{"identifier": candidate_commit, "author": "sciweave",
                    "message": _message("idem-1", "domain", base_commit, documents)}]).encode()
            if method == "GET" and "/api/document/" in path and "/commit/" in path:
                return 200, {"Content-Type": "application/json", "TerminusDB-Data-Version": f"commit:{candidate_commit}"}, json.dumps(documents).encode()
            self.fail(f"unexpected request {method} {url}")
        store = TerminusDBStore(base_url="http://terminus", request_opener=request, store_id="store", database="db")
        result = store.create_candidate_snapshot("domain", base_commit, json.dumps(documents), "idem-1")
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.commit_hash, candidate_commit)
        self.assertEqual(len(calls), 3)

    def test_branch_create_conflict_reconciles_exact_prior_candidate_only(self):
        documents = [{"@id": "TaskNode/n1", "logical_id": "n1"}]
        commit = "candidate-existing"
        writes = []
        branch_reads = 0

        def request(method, url, headers, body, timeout):
            nonlocal branch_reads
            path = urlparse(url).path
            if method == "GET" and path == "/api/db/store/db":
                branch_reads += 1
                branches = ["main"] if branch_reads == 1 else ["candidate-" + _full_key("k")]
                return 200, {}, json.dumps({"branches": branches}).encode()
            if method == "POST" and "/api/branch/" in path:
                return 409, {}, b"branch exists"
            if method == "GET" and "/api/log/" in path:
                return 200, {}, json.dumps([{"identifier": commit, "author": "sciweave",
                    "message": _message("k", "domain", "base", documents)}]).encode()
            if method == "GET" and "/api/document/" in path:
                return 200, {"Content-Type": "application/json", "TerminusDB-Data-Version": f"commit:{commit}"}, json.dumps(documents).encode()
            if method == "POST":
                writes.append(path)
                return 200, {}, b"{}"
            self.fail(f"unexpected request {method} {url}")

        store = TerminusDBStore(base_url="http://terminus", request_opener=request, store_id="store", database="db")
        result = store.create_candidate_snapshot("domain", "base", json.dumps(documents), "k")
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.commit_hash, commit)
        self.assertEqual(branch_reads, 2)
        self.assertEqual(writes, [])

    def test_branch_create_conflict_with_base_head_is_unknown_and_never_written(self):
        documents = [{"@id": "TaskNode/n1", "logical_id": "n1"}]
        writes = []
        branch_reads = 0

        def request(method, url, headers, body, timeout):
            nonlocal branch_reads
            path = urlparse(url).path
            if method == "GET" and path == "/api/db/store/db":
                branch_reads += 1
                branches = ["main"] if branch_reads == 1 else ["candidate-" + _full_key("k")]
                return 200, {}, json.dumps({"branches": branches}).encode()
            if method == "POST" and "/api/branch/" in path:
                return 409, {}, b"branch exists"
            if method == "GET" and "/api/log/" in path:
                return 200, {}, b'[{"identifier":"base","author":"someone-else","message":"unrelated"}]'
            if method == "POST":
                writes.append(path)
                return 200, {}, b"{}"
            self.fail(f"unexpected request {method} {url}")

        store = TerminusDBStore(base_url="http://terminus", request_opener=request, store_id="store", database="db")
        result = store.create_candidate_snapshot("domain", "base", json.dumps(documents), "k")
        self.assertEqual(result.status, "unknown")
        self.assertEqual(branch_reads, 2)
        self.assertEqual(writes, [])

    def test_branch_create_5xx_reconciles_exact_candidate(self):
        documents = [{"@id": "TaskNode/n1", "logical_id": "n1"}]
        commit = "candidate-after-5xx"
        branch_reads = 0

        def request(method, url, headers, body, timeout):
            nonlocal branch_reads
            path = urlparse(url).path
            if method == "GET" and path == "/api/db/store/db":
                branch_reads += 1
                branches = ["main"] if branch_reads == 1 else ["candidate-" + _full_key("k")]
                return 200, {}, json.dumps({"branches": branches}).encode()
            if method == "POST" and "/api/branch/" in path:
                return 500, {}, b"created but response failed"
            if method == "GET" and "/api/log/" in path:
                return 200, {}, json.dumps([{"identifier": commit, "author": "sciweave",
                    "message": _message("k", "domain", "base", documents)}]).encode()
            if method == "GET" and "/api/document/" in path:
                return 200, {"Content-Type": "application/json", "TerminusDB-Data-Version": f"commit:{commit}"}, json.dumps(documents).encode()
            self.fail(f"unexpected request {method} {url}")

        store = TerminusDBStore(base_url="http://terminus", request_opener=request, store_id="store", database="db")
        result = store.create_candidate_snapshot("domain", "base", json.dumps(documents), "k")
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.commit_hash, commit)
        self.assertEqual(branch_reads, 2)

    def test_branch_create_5xx_with_only_base_head_remains_unknown(self):
        documents = [{"@id": "TaskNode/n1", "logical_id": "n1"}]
        writes = []
        branch_reads = 0

        def request(method, url, headers, body, timeout):
            nonlocal branch_reads
            path = urlparse(url).path
            if method == "GET" and path == "/api/db/store/db":
                branch_reads += 1
                branches = ["main"] if branch_reads == 1 else ["candidate-" + _full_key("k")]
                return 200, {}, json.dumps({"branches": branches}).encode()
            if method == "POST" and "/api/branch/" in path:
                return 500, {}, b"created but response failed"
            if method == "GET" and "/api/log/" in path:
                return 200, {}, b'[{"identifier":"base","author":"sciweave","message":"base"}]'
            if method == "POST":
                writes.append(path)
                return 200, {}, b"{}"
            self.fail(f"unexpected request {method} {url}")

        store = TerminusDBStore(base_url="http://terminus", request_opener=request, store_id="store", database="db")
        result = store.create_candidate_snapshot("domain", "base", json.dumps(documents), "k")
        self.assertEqual(result.status, "unknown")
        self.assertEqual(branch_reads, 2)
        self.assertEqual(writes, [])

    def test_existing_branch_with_wrong_marker_or_author_is_not_reconciled(self):
        documents = [{"@id": "TaskNode/n1", "logical_id": "n1"}]
        for author, message in (("sciweave", "foreign-marker"), ("someone-else", _message("k", "domain", "base", documents))):
            with self.subTest(author=author, message=message):
                writes = []

                def request(method, url, headers, body, timeout):
                    path = urlparse(url).path
                    if method == "GET" and path == "/api/db/store/db":
                        return 200, {}, json.dumps({"branches": ["candidate-" + _full_key("k")]}).encode()
                    if method == "GET" and "/api/log/" in path:
                        return 200, {}, json.dumps([{"identifier": "foreign-commit", "author": author, "message": message}]).encode()
                    if method == "GET" and "/api/document/" in path:
                        return 200, {"Content-Type": "application/json", "TerminusDB-Data-Version": "commit:foreign-commit"}, json.dumps(documents).encode()
                    if method == "POST":
                        writes.append(path)
                        return 200, {}, b"{}"
                    self.fail(f"unexpected request {method} {url}")

                store = TerminusDBStore(base_url="http://terminus", request_opener=request, store_id="store", database="db")
                result = store.create_candidate_snapshot("domain", "base", json.dumps(documents), "k")
                self.assertEqual(result.status, "unknown")
                self.assertEqual(writes, [])

    def test_foreign_existing_branch_at_base_is_not_overwritten(self):
        documents = [{"@id": "TaskNode/n1", "logical_id": "n1"}]
        writes = []

        def request(method, url, headers, body, timeout):
            path = urlparse(url).path
            if method == "GET" and path == "/api/db/store/db":
                return 200, {}, json.dumps({"branches": ["candidate-" + _full_key("k")]}).encode()
            if method == "GET" and "/api/log/" in path:
                return 200, {}, json.dumps([{"identifier": "base", "author": "someone-else", "message": "unrelated"}]).encode()
            if method == "POST":
                writes.append(path)
                return 200, {}, b"{}"
            self.fail(f"unexpected request {method} {url}")

        store = TerminusDBStore(base_url="http://terminus", request_opener=request, store_id="store", database="db")
        result = store.create_candidate_snapshot("domain", "base", json.dumps(documents), "k")
        self.assertEqual(result.status, "unknown")
        self.assertEqual(writes, [])

    def test_inherited_documents_are_allowed_but_candidate_must_match_exactly(self):
        candidate = [{"@id": "TaskNode/n1", "logical_id": "n1"}]
        inherited = [{"@id": "TaskNode/base", "logical_id": "base"}]
        for actual, expected_status in (
            (inherited + candidate, "confirmed"),
            (inherited + [{"@id": "TaskNode/n1", "logical_id": "altered"}], "unknown"),
            (inherited, "unknown"),
        ):
            with self.subTest(actual=actual):
                def request(method, url, headers, body, timeout):
                    path = urlparse(url).path
                    if method == "GET" and path == "/api/db/store/db":
                        return 200, {}, json.dumps({"branches": ["candidate-" + _full_key("k")]}).encode()
                    if method == "GET" and "/api/log/" in path:
                        return 200, {}, json.dumps([{"identifier": "commit", "author": "sciweave",
                            "message": _message("k", "domain", "base", candidate)}]).encode()
                    if method == "GET" and "/api/document/" in path:
                        return 200, {"Content-Type": "application/json", "TerminusDB-Data-Version": "commit:commit"}, json.dumps(actual).encode()
                    self.fail(f"unexpected request {method} {url}")
                store = TerminusDBStore(base_url="http://terminus", request_opener=request, store_id="store", database="db")
                result = store.create_candidate_snapshot("domain", "base", json.dumps(candidate), "k")
                self.assertEqual(result.status, expected_status)

    def test_candidate_payload_mismatch_is_unknown(self):
        candidate = [{"@id": "TaskNode/n1", "logical_id": "n1"}]
        altered = [{"@id": "TaskNode/n1", "logical_id": "changed"}]

        def request(method, url, headers, body, timeout):
            path = urlparse(url).path
            if method == "GET" and path == "/api/db/store/db":
                return 200, {}, json.dumps({"branches": ["candidate-" + _full_key("k")]}).encode()
            if method == "GET" and "/api/log/" in path:
                return 200, {}, json.dumps([{"identifier": "commit", "author": "sciweave",
                    "message": _message("k", "domain", "base", candidate)}]).encode()
            if method == "GET" and "/api/document/" in path:
                return 200, {"Content-Type": "application/json", "TerminusDB-Data-Version": "commit:commit"}, json.dumps(altered).encode()
            self.fail(f"unexpected request {method} {url}")

        store = TerminusDBStore(base_url="http://terminus", request_opener=request, store_id="store", database="db")
        result = store.create_candidate_snapshot("domain", "base", json.dumps(candidate), "k")
        self.assertEqual(result.status, "unknown")


def _full_key(key):
    import hashlib
    return hashlib.sha256(key.encode()).hexdigest()


def _message(key, domain, base, documents):
    import hashlib
    from research_mapping.canonical import canonical_json
    digest = hashlib.sha256(canonical_json(documents).encode()).hexdigest()
    return f"sciweave-candidate:{_full_key(key)}:{domain}:{base}:{digest}"
