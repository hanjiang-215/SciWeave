from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from llm_wiki.review import WikiReviewService
from llm_wiki.formal_domain import WikiSnapshotRead
from llm_wiki.sqlite_store import SqliteStore
from llm_wiki.canonical import sha256_json


class Snapshots:
    def __init__(self, candidate): self.candidate = candidate
    def read_exact_snapshot(self, store, db, branch, commit):
        docs = self.candidate if commit == "candidate-head" else []
        return WikiSnapshotRead.confirmed(store_id=store, database=db, branch_id=branch, commit_hash=commit, documents=docs, content_digest=sha256_json(docs))

    def read_branch_head(self, store, db, branch):
        return getattr(self, "head", "candidate-head")


class Reviews(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = SqliteStore(str(Path(self.tmp.name) / "wiki.db")); self.db.initialize()
        self.db.add_formal_revision(formal_revision_id="base", wiki_domain_id="d", terminus_store_id="s", formal_branch_id="main", formal_commit_hash="base-commit")
        self.db.set_current_formal_revision("d", "base")
        docs = [{"@type":"WikiRevision", "wiki_revision_id":"r2", "document_id":"doc", "title":"new", "body_markdown":"candidate", "lifecycle_state":"candidate"}]
        self.db.connection().__enter__().execute if False else None
        with self.db.connection() as c:
            c.execute("INSERT INTO wiki_proposal VALUES (?,?,?,?,?,?,?,?)", ("p","d","base","s","candidate-branch","candidate","owner","now"))
            c.execute("INSERT INTO wiki_candidate_commit VALUES (?,?,?,?,?,?,?,?,?,?,?)", ("cc","d","p","s","candidate-branch","candidate-head","base","digest",sha256_json(docs),"author","now")); c.commit()
        self.store = Snapshots(docs)
        self.service = WikiReviewService(sqlite_store=self.db, terminus_store=self.store, terminus_database="wiki-db")
    def tearDown(self): self.tmp.cleanup()
    def test_preview_locks_exact_base_and_candidate_and_owner_decision_is_separate(self):
        preview = self.service.preview("p")
        self.assertEqual(preview.status, "ready")
        self.assertEqual(preview.base_formal_revision_id, "base")
        mr = self.service.create_merge_request("p", "mr", "curator")
        self.assertEqual(mr.status, "ready_for_owner")
        with self.db.connection() as c:
            locked = c.execute("SELECT locked_preview_id,candidate_head,base_formal_revision_id,candidate_commit_id FROM wiki_merge_request_buffer WHERE merge_request_id='mr'").fetchone()
            evidence = c.execute("SELECT preview_id,merge_request_id FROM wiki_review_evidence WHERE merge_request_id='mr'").fetchone()
        self.assertEqual(locked["locked_preview_id"], mr.preview_id)
        self.assertEqual(evidence["preview_id"], mr.preview_id)
        self.assertEqual((locked["candidate_head"],locked["base_formal_revision_id"],locked["candidate_commit_id"]),("candidate-head","base","cc"))
        rejected = self.service.decide("mr", actor_id="owner", decision="rejected", reason="revise", selected_solution_id="cc")
        self.assertEqual(rejected.status, "rejected")
    def test_owner_decision_fails_closed_without_authorization_verifier(self):
        self.service.create_merge_request("p", "mr", "curator")
        result = self.service.decide("mr", actor_id="owner", decision="approved", reason="publish", selected_solution_id="cc")
        self.assertEqual((result.status, result.reason_code), ("rejected", "owner_authorization_unverified"))

    def test_preview_detects_conflicting_duplicate_object_identity(self):
        self.store.candidate = [
            {"@type":"WikiRevision", "wiki_revision_id":"same", "document_id":"doc", "title":"one"},
            {"@type":"WikiRevision", "wiki_revision_id":"same", "document_id":"doc", "title":"two"},
        ]
        result = self.service.preview("p")
        self.assertEqual(result.reason_code, "object_conflict")
        self.assertEqual(result.status, "conflict")

    def test_stale_head_or_base_cannot_be_approved(self):
        self.db.set_current_formal_revision("d", None)
        self.assertEqual(self.service.preview("p").status, "stale_base")

    def test_preview_and_owner_decision_reject_candidate_branch_head_changes(self):
        preview = self.service.preview("p")
        self.assertEqual(preview.status, "ready")
        self.assertEqual(self.service.create_merge_request("p", "mr", "curator").status, "ready_for_owner")
        self.store.head = "new-head"
        self.assertEqual(self.service.preview("p").reason_code, "candidate_head_changed")
        result = self.service.decide("mr", actor_id="owner", decision="approved", reason="publish", selected_solution_id="cc")
        self.assertEqual((result.status, result.reason_code), ("rejected", "candidate_head_changed"))

    def test_preview_refuses_a_base_revision_that_has_no_record(self):
        # ai4-qstm: the pointer and the proposal can agree on a revision id whose
        # row is gone (deleted, or an empty base written before any formal
        # revision existed). preview used to raise AttributeError on base.*.
        with self.db.connection() as c:
            c.execute("DELETE FROM formal_wiki_revision WHERE formal_wiki_revision_id = 'base'")
            c.commit()

        result = self.service.preview("p")

        self.assertEqual((result.status, result.reason_code), ("unavailable", "base_missing"))

    def test_a_missing_base_also_blocks_the_owner_decision(self):
        with self.db.connection() as c:
            c.execute("DELETE FROM formal_wiki_revision WHERE formal_wiki_revision_id = 'base'")
            c.commit()

        result = self.service.create_merge_request("p", "mr", "curator")

        self.assertNotEqual(result.status, "ready_for_owner")


if __name__ == "__main__": unittest.main()
