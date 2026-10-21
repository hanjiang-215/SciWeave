from __future__ import annotations

import os
import tempfile
import unittest
from typing import Any

from research_mapping.domain import FormalMappingRevision
from research_mapping.sqlite_store import SqliteStore
from research_mapping.candidate_submission import MappingCandidateService


DOMAIN = "domain-1"
BASE = "formal-1"


def node(logical_id: str = "n1", version_id: str = "n1-v1") -> dict[str, Any]:
    return {
        "@type": "TaskNode", "mapping_domain_id": DOMAIN,
        "logical_id": logical_id, "version_id": version_id,
        "title": logical_id, "objective": "objective", "scope": "scope",
        "acceptance_criteria": ["check"], "expected_outputs": ["result"],
        "required_evidence": ["evidence"], "task_owner_id": "owner",
        "lifecycle_state": "candidate", "proposal_id": "proposal-1",
        "base_formal_revision_id": BASE, "created_by": "hanjiang",
        "created_at": "2026-10-21T00:00:00Z",
    }


def change_set(nodes=None, edges=None, **overrides):
    payload = {
        "mapping_domain_id": DOMAIN, "submitter_id": "hanjiang",
        "submission_id": "submission-1", "proposal_id": "proposal-1", "base_formal_revision_id": BASE,
        "nodes": nodes if nodes is not None else [node()],
        "edges": edges if edges is not None else [],
    }
    payload.update(overrides)
    for item in payload["nodes"]:
        item["proposal_id"] = payload["proposal_id"]
    for item in payload["edges"]:
        item["proposal_id"] = payload["proposal_id"]
    return payload


class FakeTerminus:
    def __init__(self, outcome="confirmed"):
        self.outcome = outcome
        self.calls = []

    def create_candidate_snapshot(self, domain_id, base_commit_ref, canonical_snapshot, idempotency_key):
        self.calls.append((domain_id, base_commit_ref, canonical_snapshot, idempotency_key))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        if self.outcome == "unknown":
            return {"status": "unknown"}
        if self.outcome == "failed":
            return {"status": "failed", "reason_code": "store_rejected"}
        return {"status": "confirmed", "store_id": "store", "branch_id": "candidate/submission-1",
                "commit_hash": "commit-1"}


class CandidateSubmissionTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sqlite = SqliteStore(os.path.join(self.tmp.name, "mapping.db"))
        self.sqlite.initialize()
        self.sqlite.add_formal_revision(FormalMappingRevision(
            formal_revision_id=BASE, mapping_domain_id=DOMAIN,
            terminus_store_id="store", formal_branch_id="formal",
            formal_commit_hash="base-commit", base_formal_revision_id=None,
            source_proposal_id=None, approval_audit_event_id=None,
            published_by="owner", published_at="2026-10-21T00:00:00Z"))
        self.sqlite.set_current_formal_revision(DOMAIN, BASE, updated_at="2026-10-21T00:00:00Z")
        self.terminus = FakeTerminus()
        self.service = MappingCandidateService(self.sqlite, self.terminus, terminus_database="db")

    def submit(self, cs=None, key="key-1"):
        return self.service.submit(cs or change_set(), key)

    def test_success_persists_governance_and_candidate_identity(self):
        result = self.submit()
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.submission_id, "submission-1")
        self.assertEqual(result.proposal_id, "proposal-1")
        self.assertEqual(result.candidate_commit_id, "candidate-commit-" + __import__("hashlib").sha256(b"key-1").hexdigest()[:16])
        self.assertEqual(result.commit_hash, "commit-1")
        self.assertEqual(self.sqlite.get_current_formal_revision_id(DOMAIN), BASE)
        self.assertEqual(self.submit(), result)
        self.assertEqual(len(self.terminus.calls), 1)
        self.assertEqual(self.sqlite.count_candidate_records(), (1, 1, 1, 1))

    def test_idempotency_conflict_does_not_replace_candidate(self):
        self.submit()
        result = self.submit(change_set(nodes=[node(version_id="n1-v2")]))
        self.assertEqual(result.reason_code, "idempotency_conflict")
        self.assertEqual(len(self.terminus.calls), 1)

    def test_relationship_validation_rejects_missing_target_and_self_loop(self):
        edge = {"@type": "DependencyEdge", "mapping_domain_id": DOMAIN,
                "logical_id": "e1", "version_id": "e1-v1",
                "source_node_version_ref": {"logical_id": "n1", "version_id": "n1-v1"},
                "target_node_version_ref": {"logical_id": "missing", "version_id": "x"},
                "dependency_kind": "information", "lifecycle_state": "candidate",
                "proposal_id": "proposal-1", "base_formal_revision_id": BASE}
        self.assertEqual(self.submit(change_set(edges=[edge])).reason_code, "missing_relation_target")
        edge["target_node_version_ref"] = edge["source_node_version_ref"]
        self.assertEqual(self.submit(change_set(edges=[edge], submission_id="submission-2", proposal_id="proposal-2"), key="key-2").reason_code, "self_loop")
        self.assertEqual(self.terminus.calls, [])

    def test_blocking_cycle_is_rejected(self):
        nodes = [node("a", "a1"), node("b", "b1")]
        edges = []
        for logical_id, source, target in (("e1", "a", "b"), ("e2", "b", "a")):
            edges.append({"@type": "DependencyEdge", "mapping_domain_id": DOMAIN,
                "logical_id": logical_id, "version_id": logical_id + "v1",
                "source_node_version_ref": {"logical_id": source, "version_id": source + "1"},
                "target_node_version_ref": {"logical_id": target, "version_id": target + "1"},
                "dependency_kind": "blocking", "required_outputs": ["out"],
                "blocks_until": "accepted", "lifecycle_state": "candidate",
                "proposal_id": "proposal-1", "base_formal_revision_id": BASE})
        self.assertEqual(self.submit(change_set(nodes=nodes, edges=edges)).reason_code, "blocking_cycle")
        self.assertEqual(self.terminus.calls, [])

    def test_expired_base_rejected(self):
        self.sqlite.add_formal_revision(FormalMappingRevision(
            formal_revision_id="other", mapping_domain_id=DOMAIN,
            terminus_store_id="store", formal_branch_id="formal",
            formal_commit_hash="other-commit", base_formal_revision_id=BASE,
            source_proposal_id=None, approval_audit_event_id=None,
            published_by="owner", published_at="now"))
        self.sqlite.set_current_formal_revision(DOMAIN, "other", updated_at="now")
        result = self.submit()
        self.assertEqual(result.reason_code, "stale_base")
        self.assertEqual(self.terminus.calls, [])

    def test_validation_errors_include_required_fields_and_lifecycle(self):
        bad = node()
        bad["acceptance_criteria"] = []
        self.assertEqual(self.submit(change_set(nodes=[bad])).reason_code, "invalid_task_node")

    def test_terminus_failure_and_unknown_are_not_success(self):
        self.terminus.outcome = "failed"
        self.assertEqual(self.submit().status, "failed")
        self.terminus.outcome = "unknown"
        result = self.submit(change_set(submission_id="submission-2", proposal_id="proposal-2"), key="key-2")
        self.assertEqual(result.status, "result_unknown")
        self.assertIsNone(result.commit_hash)
        self.assertEqual(self.sqlite.count_candidate_records(), (2, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
