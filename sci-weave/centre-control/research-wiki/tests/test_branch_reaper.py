"""ai4-4g9s: reaping candidate branches only drops branches no longer in use."""

from __future__ import annotations

import json
import unittest

from llm_wiki.branch_reaper import active_candidate_branches, reap_candidate_branches
from llm_wiki.terminus_store import TerminusDBWikiCandidateStore

DOMAIN = "wiki-1"


class _FakeSqlite:
    def __init__(self, rows):
        self._rows = rows

    def list_dashboard_candidates(self, wiki_domain_id):
        return [row for row in self._rows if row.get("wiki_domain_id", DOMAIN) == wiki_domain_id]


class _ReapableStore:
    def __init__(self, branches, fail_delete=()):
        self._branches = list(branches)
        self._fail = set(fail_delete)
        self.deleted = []

    def list_candidate_branches(self):
        return list(self._branches)

    def reap_candidate_branches(self, keep):
        deleted = []
        failed = []
        for branch in self._branches:
            if branch in keep:
                continue
            if branch in self._fail:
                failed.append(branch)
            else:
                deleted.append(branch)
                self.deleted.append(branch)
        return {"deleted": deleted, "failed": failed, "skipped": []}


class ActiveBranchTests(unittest.TestCase):
    def test_only_non_terminal_submissions_are_active(self):
        rows = [
            {"branch_id": "wiki-candidate-active", "proposal_status": "review_pending", "submission_status": "pending"},
            {"branch_id": "wiki-candidate-merged", "proposal_status": "merged", "submission_status": "pending"},
            {"branch_id": "wiki-candidate-rejected", "proposal_status": "rejected", "submission_status": "pending"},
            {"branch_id": None, "proposal_status": "review_pending", "submission_status": "pending"},
        ]
        self.assertEqual(active_candidate_branches(_FakeSqlite(rows), DOMAIN), {"wiki-candidate-active"})


class ReapTests(unittest.TestCase):
    def _rows(self):
        return [
            {"branch_id": "wiki-candidate-active", "proposal_status": "review_pending", "submission_status": "pending"},
            {"branch_id": "wiki-candidate-merged", "proposal_status": "merged", "submission_status": "pending"},
        ]

    def test_reap_deletes_terminal_and_keeps_active(self):
        branches = ["wiki-candidate-active", "wiki-candidate-merged", "wiki-candidate-orphan"]
        store = _ReapableStore(branches)
        result = reap_candidate_branches(sqlite_store=_FakeSqlite(self._rows()), terminus_store=store, wiki_domain_id=DOMAIN)
        self.assertEqual(sorted(result.deleted), ["wiki-candidate-merged", "wiki-candidate-orphan"])
        self.assertEqual(store.deleted, ["wiki-candidate-merged", "wiki-candidate-orphan"])
        self.assertEqual(result.kept_active, ["wiki-candidate-active"])

    def test_dry_run_deletes_nothing(self):
        branches = ["wiki-candidate-active", "wiki-candidate-merged"]
        store = _ReapableStore(branches)
        result = reap_candidate_branches(
            sqlite_store=_FakeSqlite(self._rows()), terminus_store=store, wiki_domain_id=DOMAIN, dry_run=True
        )
        self.assertEqual(result.deleted, ["wiki-candidate-merged"])
        self.assertEqual(store.deleted, [])

    def test_failed_deletes_are_reported(self):
        branches = ["wiki-candidate-merged", "wiki-candidate-orphan"]
        store = _ReapableStore(branches, fail_delete={"wiki-candidate-orphan"})
        result = reap_candidate_branches(sqlite_store=_FakeSqlite(self._rows()), terminus_store=store, wiki_domain_id=DOMAIN)
        self.assertEqual(result.deleted, ["wiki-candidate-merged"])
        self.assertEqual(result.failed, ["wiki-candidate-orphan"])


class StoreGuardTests(unittest.TestCase):
    """The store itself must refuse to touch anything off the candidate namespace."""

    def test_delete_refuses_non_candidate_branch(self):
        store = TerminusDBWikiCandidateStore(store_id="s", database="d", base_url="http://unused")
        with self.assertRaises(ValueError):
            store.delete_candidate_branch("main")
        with self.assertRaises(ValueError):
            store.delete_candidate_branch("some-other-branch")

    def test_list_filters_to_candidate_prefix(self):
        store = TerminusDBWikiCandidateStore(
            store_id="s", database="d", base_url="http://unused",
            request_opener=lambda method, url, headers, body, timeout: (
                200, {}, json.dumps({"branches": ["main", "wiki-candidate-a", "other"]}).encode()
            ),
        )
        self.assertEqual(store.list_candidate_branches(), ["wiki-candidate-a"])


if __name__ == "__main__":
    unittest.main()
