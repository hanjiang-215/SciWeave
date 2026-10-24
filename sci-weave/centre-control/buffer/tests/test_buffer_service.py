from __future__ import annotations

import unittest

from draft_buffer import BufferError
from draft_buffer.config import BufferConfig
from draft_buffer.main import dispatch
from draft_buffer.service import DraftBufferService


class MemoryStore:
    def __init__(self):
        self.documents = []
        self.writes = 0

    def initialize_schema(self):
        return None

    def read_all(self):
        return [dict(item) for item in self.documents]

    def write(self, documents, operation, idempotency_key):
        self.writes += 1
        self.documents = [dict(item) for item in documents]
        return f"commit-{self.writes}"


class DraftBufferServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.service = DraftBufferService(self.store, {"mapping": frozenset({"reviewer-map"}), "wiki": frozenset({"reviewer-wiki"})})

    def create(self, key="create-key"):
        return self.service.create_draft("wiki", "wiki_document", "Evidence", {"body":"draft"}, "researcher", key)

    def test_create_and_repeat_same_key_returns_first_result(self):
        first = self.create()
        second = self.create()
        self.assertEqual(first["draft_id"], second["draft_id"])
        self.assertEqual(self.store.writes, 1)

    def test_reusing_key_for_different_request_is_rejected(self):
        self.create()
        with self.assertRaisesRegex(BufferError, "idempotency key"):
            self.service.create_draft("wiki", "wiki_document", "Other", {}, "researcher", "create-key")

    def test_submit_freezes_commit_before_review(self):
        draft = self.create()
        submitted = self.service.submit_draft(draft["draft_id"], "submit-key", actor_id="researcher")
        self.assertEqual(submitted["status"], "submitted")
        stored = self.service.read_draft(draft["draft_id"], actor_id="reviewer-wiki")["draft"]
        self.assertEqual(stored["submitted_commit"], "commit-2")

    def test_only_configured_namespace_reviewer_can_review(self):
        draft = self.create()
        self.service.submit_draft(draft["draft_id"], "submit-key", actor_id="researcher")
        with self.assertRaisesRegex(BufferError, "not authorized"):
            self.service.review_draft(draft["draft_id"], "accept", "looks good", "review-key", actor_id="outsider")
        decision = self.service.review_draft(draft["draft_id"], "accept", "reviewed", "review-key", actor_id="reviewer-wiki")
        self.assertEqual(decision["status"], "accepted")

    def test_repeated_review_does_not_create_a_second_decision(self):
        draft = self.create()
        self.service.submit_draft(draft["draft_id"], "submit-key", actor_id="researcher")
        first = self.service.review_draft(draft["draft_id"], "accept", "reviewed", "review-key", actor_id="reviewer-wiki")
        writes = self.store.writes
        second = self.service.review_draft(draft["draft_id"], "accept", "reviewed", "review-key", actor_id="reviewer-wiki")
        self.assertEqual(first["status"], second["status"])
        self.assertEqual(self.store.writes, writes)

    def test_same_namespace_policy_is_visible_and_other_namespace_is_not(self):
        wiki = self.create()
        mapping = self.service.create_draft("mapping", "mapping_change", "Route", {}, "researcher", "mapping-create")
        self.assertEqual([row["draft_id"] for row in self.service.list_drafts("wiki", actor_id="reviewer-wiki")], [wiki["draft_id"]])
        with self.assertRaisesRegex(BufferError, "not authorized"):
            self.service.list_drafts("mapping", actor_id="reviewer-wiki")

    def test_candidate_promotion_records_exact_id_and_commit(self):
        draft = self.create()
        self.service.submit_draft(draft["draft_id"], "submit-key", actor_id="researcher")
        self.service.review_draft(draft["draft_id"], "accept", "reviewed", "review-key", actor_id="reviewer-wiki")
        result = self.service.mark_promoted(draft["draft_id"], "proposal-1", "commit-abc", "promote-key", actor_id="reviewer-wiki")
        stored = self.service.read_draft(draft["draft_id"], actor_id="reviewer-wiki")["draft"]
        self.assertEqual(result["status"], "promoted")
        self.assertEqual(stored["promoted_candidate_commit"], "commit-abc")

    def test_mcp_lists_seven_tools_and_dispatches_calls(self):
        listed = dispatch(self.service, {"jsonrpc":"2.0", "id":1, "method":"tools/list"})
        self.assertEqual(len(listed["result"]["tools"]), 7)
        result = dispatch(self.service, {"jsonrpc":"2.0", "id":2, "method":"tools/call", "params":{"name":"create_draft", "arguments":{"namespace":"wiki", "kind":"wiki_document", "title":"Page", "payload":{}, "submitted_by":"researcher", "idempotency_key":"mcp-key"}}, "_trusted_actor_id":"researcher"})
        self.assertFalse(result["result"]["isError"])

    def test_promoted_draft_is_readonly_and_cannot_be_reviewed_or_submitted_again(self):
        draft = self.create()
        self.service.submit_draft(draft["draft_id"], "submit-key", actor_id="researcher")
        self.service.review_draft(draft["draft_id"], "accept", "reviewed", "review-key", actor_id="reviewer-wiki")
        self.service.mark_promoted(draft["draft_id"], "proposal-1", "commit-abc", "promote-key", actor_id="reviewer-wiki")
        with self.assertRaisesRegex(BufferError, "not editable"):
            self.service.update_draft(draft["draft_id"], "edit-key", title="Changed", actor_id="researcher")
        with self.assertRaisesRegex(BufferError, "cannot be submitted"):
            self.service.submit_draft(draft["draft_id"], "submit-again-key", actor_id="researcher")
        with self.assertRaisesRegex(BufferError, "only a submitted snapshot may be reviewed"):
            self.service.review_draft(draft["draft_id"], "reject", "late", "review-again-key", actor_id="reviewer-wiki")

    def test_rejected_draft_revision_creates_new_identity_and_freezes_fresh_commit(self):
        draft = self.create()
        self.service.submit_draft(draft["draft_id"], "submit-key", actor_id="researcher")
        self.service.review_draft(draft["draft_id"], "reject", "needs evidence", "review-key", actor_id="reviewer-wiki")
        revised = self.service.update_draft(draft["draft_id"], "revision-key", payload={"body": "revised"}, actor_id="researcher")
        self.assertNotEqual(revised["draft_id"], draft["draft_id"])
        self.assertEqual(revised["status"], "drafting")
        resubmitted = self.service.submit_draft(revised["draft_id"], "resubmit-key", actor_id="researcher")
        self.assertEqual(resubmitted["status"], "submitted")
        stored_revised = self.service.read_draft(revised["draft_id"], actor_id="reviewer-wiki")["draft"]
        self.assertEqual(stored_revised["payload"], {"body": "revised"})
        self.assertTrue(stored_revised["submitted_commit"])
        stored_original = self.service.read_draft(draft["draft_id"], actor_id="reviewer-wiki")["draft"]
        self.assertEqual(stored_original["payload"], {"body": "draft"})
        self.assertEqual(stored_original["supersedes_draft_id"], None)

    def test_editing_a_submitted_draft_does_not_change_the_review_snapshot(self):
        draft = self.create()
        self.service.submit_draft(draft["draft_id"], "submit-key", actor_id="researcher")
        frozen = self.service.read_draft(draft["draft_id"], actor_id="reviewer-wiki")["draft"]["submitted_commit"]
        with self.assertRaisesRegex(BufferError, "not editable"):
            self.service.update_draft(draft["draft_id"], "edit-key", payload={"body": "sneaky"}, actor_id="researcher")
        after = self.service.read_draft(draft["draft_id"], actor_id="reviewer-wiki")["draft"]
        self.assertEqual(after["submitted_commit"], frozen)
        self.assertEqual(after["payload"], {"body": "draft"})

    def test_configuration_requires_addresses_and_explicit_reviewer_policy(self):
        config = BufferConfig.from_environment({
            "SCIWEAVE_BUFFER_TERMINUSDB_URL":"http://127.0.0.1:0",
            "SCIWEAVE_BUFFER_TERMINUSDB_DATABASE":"buffer-test",
            "SCIWEAVE_BUFFER_REVIEWERS_JSON":'{"mapping":["map-owner"],"wiki":["wiki-owner"]}',
        })
        self.assertEqual(config.reviewers["wiki"], frozenset({"wiki-owner"}))
        with self.assertRaises(BufferError):
            BufferConfig.from_environment({})


if __name__ == "__main__":
    unittest.main()
