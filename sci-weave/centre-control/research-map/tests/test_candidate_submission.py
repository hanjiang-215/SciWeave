from __future__ import annotations

import os
import tempfile
import unittest
from research_mapping.domain import FormalMappingRevision
from research_mapping.sqlite_store import SqliteStore
from research_mapping.candidate_submission import MappingCandidateService

DOMAIN, BASE = "domain-1", "formal-1"

def node(logical_id="n1", version_id="n1-v1"):
    return {"@type":"TaskNode", "@id":f"TaskNode/{version_id}", "mapping_domain_id":DOMAIN, "logical_id":logical_id, "version_id":version_id,
        "title":logical_id, "objective":"objective", "scope":"scope", "acceptance_criteria":["check"],
        "expected_outputs":["result"], "required_evidence":["evidence"], "task_owner_id":"owner",
        "lifecycle_state":"candidate", "proposal_id":"proposal-1", "base_formal_revision_id":BASE,
        "created_by":"hanjiang", "created_at":"2026-10-21T00:00:00Z"}

def change_set(nodes=None, edges=None, **overrides):
    payload = {"mapping_domain_id":DOMAIN, "submitter_id":"hanjiang", "submission_id":"submission-1",
        "proposal_id":"proposal-1", "base_formal_revision_id":BASE, "nodes":nodes or [node()], "edges":edges or []}
    payload.update(overrides)
    for item in payload["nodes"]: item["proposal_id"] = payload["proposal_id"]
    return payload

class FakeTerminus:
    def __init__(self, outcome="confirmed"): self.outcome, self.calls = outcome, []
    def create_candidate_snapshot(self, domain_id, base_commit_ref, canonical_snapshot, idempotency_key):
        self.calls.append((domain_id, base_commit_ref, canonical_snapshot, idempotency_key))
        if self.outcome == "unknown": return {"status":"unknown"}
        if self.outcome == "failed": return {"status":"failed", "reason_code":"store_rejected"}
        return {"status":"confirmed", "store_id":"store", "branch_id":"candidate/submission-1", "commit_hash":"commit-1"}

class CandidateSubmissionTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.sqlite = SqliteStore(os.path.join(self.tmp.name, "mapping.db")); self.sqlite.initialize()
        self.sqlite.add_formal_revision(FormalMappingRevision(formal_revision_id=BASE, mapping_domain_id=DOMAIN,
            terminus_store_id="store", formal_branch_id="formal", formal_commit_hash="base-commit",
            base_formal_revision_id=None, source_proposal_id=None, approval_audit_event_id=None,
            published_by="owner", published_at="2026-10-21T00:00:00Z"))
        self.sqlite.set_current_formal_revision(DOMAIN, BASE, updated_at="2026-10-21T00:00:00Z")
        self.terminus = FakeTerminus(); self.service = MappingCandidateService(self.sqlite, self.terminus, terminus_database="db")
    def submit(self, cs=None, key="key-1"): return self.service.submit(cs or change_set(), key)
    def test_candidate_documents_get_distinct_version_based_terminus_ids(self):
        first = node("n1", "n1-v1")
        second = node("n1", "n1-v2")
        result = self.submit(change_set(nodes=[first, second], submission_id="versioned", proposal_id="proposal-versioned"), "versioned-key")
        self.assertEqual(result.status, "confirmed")
        documents = __import__("json").loads(self.terminus.calls[-1][2])
        self.assertEqual([document["@id"] for document in documents], ["TaskNode/n1-v1", "TaskNode/n1-v2"])

    def test_explicit_terminus_id_must_match_immutable_version_id(self):
        invalid = node()
        invalid["@id"] = "TaskNode/n1-v2"
        result = self.submit(change_set(nodes=[invalid], submission_id="wrong-document-id", proposal_id="proposal-wrong-id"), "wrong-document-id")
        self.assertEqual((result.status, result.reason_code), ("rejected", "invalid_task_node_id"))
        self.assertEqual(self.terminus.calls, [])

    def test_success_persists_governance_and_replay(self):
        result=self.submit(); self.assertEqual(result.status,"confirmed"); self.assertEqual(self.submit(),result)
        self.assertEqual(len(self.terminus.calls),1); self.assertEqual(self.sqlite.count_candidate_records(),(1,1,1,1))
    def test_idempotency_conflict_does_not_replace_candidate(self):
        self.submit(); self.assertEqual(self.submit(change_set(nodes=[node(version_id="n1-v2")])).reason_code,"idempotency_conflict")
    def test_unknown_retry_reconciles_same_identity_without_duplicates(self):
        self.terminus.outcome="unknown"; first=self.submit(); self.assertEqual(first.status,"result_unknown")
        self.terminus.outcome="confirmed"; replay=self.submit()
        self.assertEqual(replay.status,"confirmed"); self.assertEqual(replay.submission_id,first.submission_id)
        self.assertEqual(replay.proposal_id,first.proposal_id); self.assertEqual(replay.commit_hash,"commit-1")
        self.assertEqual(self.terminus.calls[0],self.terminus.calls[1]); self.assertEqual(self.sqlite.count_candidate_records(),(1,1,1,1))
    def test_unresolved_unknown_retry_remains_unknown(self):
        self.terminus.outcome="unknown"; self.assertEqual(self.submit().status,"result_unknown")
        self.assertEqual(self.submit().status,"result_unknown"); self.assertEqual(len(self.terminus.calls),2)
        self.assertEqual(self.sqlite.count_candidate_records(),(1,0,0,0))
    def test_terminus_failure_is_not_success(self):
        self.terminus.outcome="failed"; self.assertEqual(self.submit().status,"failed")

    def test_candidate_result_uses_verified_nodes_edges_digest(self):
        result = self.submit()
        from research_mapping.canonical import sha256_json

        expected_snapshot = sha256_json(change_set()["nodes"] + change_set()["edges"])
        expected_change_set = sha256_json(change_set())
        self.assertEqual(result.content_digest, expected_snapshot)
        with self.sqlite.connection() as connection:
            row = connection.execute(
                "SELECT content_digest, candidate_snapshot_digest FROM mapping_candidate_commit"
            ).fetchone()
        self.assertEqual(row["candidate_snapshot_digest"], expected_snapshot)
        self.assertEqual(row["content_digest"], expected_change_set)

    def test_persist_transaction_rolls_back_all_candidate_governance_changes(self):
        with self.sqlite.connection() as connection:
            connection.execute("""
                CREATE TRIGGER fail_candidate_audit
                BEFORE INSERT ON mapping_audit_event
                BEGIN SELECT RAISE(ABORT, 'injected audit failure'); END
            """)
            connection.commit()

        result = self.submit()
        self.assertEqual((result.status, result.reason_code), ("result_unknown", "result_unknown"))
        self.assertEqual(self.sqlite.count_candidate_records(), (1, 0, 0, 0))
        with self.sqlite.connection() as connection:
            status = connection.execute(
                "SELECT status FROM mapping_submission WHERE submission_id=?", ("submission-1",)
            ).fetchone()["status"]
        self.assertEqual(status, "pending")

    def test_dependency_edge_requires_all_candidate_fields(self):
        edge = {
            "@type": "DependencyEdge", "mapping_domain_id": DOMAIN, "logical_id": "e1", "version_id": "e1-v1",
            "source_node_version_ref": {"logical_id": "n1", "version_id": "n1-v1"},
            "target_node_version_ref": {"logical_id": "n2", "version_id": "n2-v1"},
            "dependency_kind": "information", "lifecycle_state": "candidate",
            "proposal_id": "proposal-1", "base_formal_revision_id": BASE,
            "created_by": "hanjiang", "created_at": "2026-10-21T00:00:00Z",
        }
        for field in ("mapping_domain_id", "logical_id", "version_id", "source_node_version_ref",
                      "target_node_version_ref", "dependency_kind", "lifecycle_state", "mapping_domain_id", "proposal_id",
                      "base_formal_revision_id", "created_by", "created_at"):
            invalid = dict(edge)
            invalid["created_by"] = "hanjiang"
            invalid["created_at"] = "2026-10-21T00:00:00Z"
            invalid["proposal_id"] = "proposal-" + field
            invalid["mapping_domain_id"] = DOMAIN
            invalid["base_formal_revision_id"] = BASE
            invalid.pop(field, None)
            with self.subTest(field=field):
                self.assertEqual(
                    self.submit(change_set(nodes=[node(), node("n2", "n2-v1")], edges=[invalid], submission_id="submission-" + field, proposal_id="proposal-" + field), "key-" + field).reason_code,
                    "invalid_dependency_edge",
                )

    def test_dependency_edge_rejects_duplicate_identity_and_invalid_metadata(self):
        first = {
            "@type": "DependencyEdge", "mapping_domain_id": DOMAIN, "logical_id": "e1", "version_id": "e1-v1",
            "source_node_version_ref": {"logical_id": "n1", "version_id": "n1-v1"},
            "target_node_version_ref": {"logical_id": "n2", "version_id": "n2-v1"},
            "dependency_kind": "information", "lifecycle_state": "candidate", "proposal_id": "proposal-1",
            "base_formal_revision_id": BASE, "created_by": "hanjiang", "created_at": "2026-10-21T00:00:00Z",
        }
        duplicate = dict(first)
        duplicate["source_node_version_ref"] = {"logical_id": "n1", "version_id": "n1-v1"}
        self.assertEqual(self.submit(change_set(nodes=[node(), node("n2", "n2-v1")], edges=[first, duplicate])).reason_code, "duplicate_dependency_edge")
        for field, value in (("mapping_domain_id", "other-domain"), ("proposal_id", "other-proposal"),
                             ("base_formal_revision_id", "other-base")):
            invalid = dict(first)
            invalid[field] = value
            with self.subTest(field=field):
                self.assertEqual(
                    self.submit(change_set(nodes=[node(), node("n2", "n2-v1")], edges=[invalid], submission_id="submission-" + field, proposal_id="proposal-" + field), "key-" + field).reason_code,
                    "invalid_dependency_edge",
                )

        edge={"@type":"DependencyEdge","mapping_domain_id":DOMAIN,"logical_id":"e1","version_id":"e1-v1",
            "source_node_version_ref":{"logical_id":"n1","version_id":"n1-v1"},
            "target_node_version_ref":{"logical_id":"missing","version_id":"x"},"dependency_kind":"information",
            "lifecycle_state":"candidate","proposal_id":"proposal-1","base_formal_revision_id":BASE,
            "created_by":"hanjiang","created_at":"2026-10-21T00:00:00Z"}
        self.assertEqual(self.submit(change_set(edges=[edge], submission_id="submission-missing", proposal_id="proposal-missing"), "missing-target").reason_code,"missing_relation_target")
        edge["target_node_version_ref"]=edge["source_node_version_ref"]
        self.assertEqual(self.submit(change_set(edges=[edge],submission_id="submission-2",proposal_id="proposal-2"),"key-2").reason_code,"self_loop")
        self.assertEqual(self.terminus.calls,[])
    def test_blocking_cycle_is_rejected(self):
        nodes=[node("a","a1"),node("b","b1")]; edges=[]
        for eid,source,target in (("e1","a","b"),("e2","b","a")):
            edges.append({"@type":"DependencyEdge","mapping_domain_id":DOMAIN,"logical_id":eid,"version_id":eid+"v1",
                "source_node_version_ref":{"logical_id":source,"version_id":source+"1"},
                "target_node_version_ref":{"logical_id":target,"version_id":target+"1"},"dependency_kind":"blocking",
                "required_outputs":["out"],"blocks_until":"accepted","lifecycle_state":"candidate",
                "proposal_id":"proposal-1","base_formal_revision_id":BASE,"created_by":"hanjiang",
                "created_at":"2026-10-21T00:00:00Z"})
        self.assertEqual(self.submit(change_set(nodes=nodes,edges=edges)).reason_code,"blocking_cycle")
        self.assertEqual(self.terminus.calls,[])
    def test_expired_base_is_rejected(self):
        self.sqlite.add_formal_revision(FormalMappingRevision(formal_revision_id="other",mapping_domain_id=DOMAIN,
            terminus_store_id="store",formal_branch_id="formal",formal_commit_hash="other-commit",
            base_formal_revision_id=BASE,source_proposal_id=None,approval_audit_event_id=None,published_by="owner",published_at="now"))
        self.sqlite.set_current_formal_revision(DOMAIN,"other",updated_at="now")
        self.assertEqual(self.submit().reason_code,"stale_base"); self.assertEqual(self.terminus.calls,[])
    def test_validation_rejects_missing_required_values(self):
        invalid=node(); invalid["acceptance_criteria"]=[]
        self.assertEqual(self.submit(change_set(nodes=[invalid])).reason_code,"invalid_task_node")
    def test_unknown_retry_reconciles_stale_base_but_never_persists_candidate(self):
        self.terminus.outcome="unknown"
        self.assertEqual(self.submit().status,"result_unknown")
        self.sqlite.add_formal_revision(FormalMappingRevision(formal_revision_id="advanced",mapping_domain_id=DOMAIN,
            terminus_store_id="store",formal_branch_id="formal",formal_commit_hash="advanced-commit",
            base_formal_revision_id=BASE,source_proposal_id=None,approval_audit_event_id=None,published_by="owner",published_at="now"))
        self.sqlite.set_current_formal_revision(DOMAIN,"advanced",updated_at="now")
        self.terminus.outcome="confirmed"
        replay=self.submit()
        self.assertEqual(replay.status,"rejected")
        self.assertEqual(replay.reason_code,"stale_base")
        self.assertEqual(len(self.terminus.calls),2)
        self.assertEqual(self.terminus.calls[0],self.terminus.calls[1])
        self.assertEqual(self.sqlite.count_candidate_records(),(1,0,0,0))
    def test_unknown_retry_reconciles_when_stored_base_metadata_is_missing(self):
        self.terminus.outcome="unknown"
        self.assertEqual(self.submit().status,"result_unknown")
        with self.sqlite.connection() as connection:
            connection.execute("UPDATE mapping_submission SET base_formal_revision_id=NULL WHERE idempotency_key=?", ("key-1",))
            connection.commit()
        replay=self.submit()
        self.assertEqual(replay.status,"result_unknown")
        self.assertEqual(replay.reason_code,"store_result_unknown")
        self.assertEqual(len(self.terminus.calls),2)
        self.assertEqual(self.terminus.calls[1][1],"base-commit")

    def test_production_adapter_result_dataclass_is_handled_by_service(self):
        from research_mapping.terminus_store import CandidateSnapshotResult

        self.terminus.create_candidate_snapshot = lambda *args: CandidateSnapshotResult(
            "confirmed", "store", "candidate-branch", "commit-1"
        )
        result = self.submit()
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.branch_id, "candidate-branch")
        self.assertEqual(self.sqlite.count_candidate_records(), (1, 1, 1, 1))

    def test_production_adapter_explicit_failure_is_handled_by_service(self):
        from research_mapping.terminus_store import CandidateSnapshotResult

        self.terminus.create_candidate_snapshot = lambda *args: CandidateSnapshotResult(
            "failed", reason_code="store_rejected"
        )
        result = self.submit()
        self.assertEqual((result.status, result.reason_code), ("failed", "store_rejected"))
        self.assertEqual(self.sqlite.count_candidate_records(), (1, 0, 0, 0))

    def test_formal_pointer_change_during_store_call_prevents_persistence(self):
        original = self.terminus.create_candidate_snapshot

        def advance_pointer(*args):
            result = original(*args)
            self.sqlite.add_formal_revision(FormalMappingRevision(formal_revision_id="advanced",
                mapping_domain_id=DOMAIN, terminus_store_id="store", formal_branch_id="formal",
                formal_commit_hash="advanced-commit", base_formal_revision_id=BASE,
                source_proposal_id=None, approval_audit_event_id=None, published_by="owner", published_at="now"))
            self.sqlite.set_current_formal_revision(DOMAIN, "advanced", updated_at="now")
            return result

        self.terminus.create_candidate_snapshot = advance_pointer
        result = self.submit()
        self.assertEqual((result.status, result.reason_code), ("rejected", "stale_base"))
        self.assertEqual(self.sqlite.count_candidate_records(), (1, 0, 0, 0))

    def test_initial_empty_base_is_rejected_without_store_write(self):
        result = self.submit(change_set(base_formal_revision_id=None, nodes=[node() | {"base_formal_revision_id": None}]))
        self.assertEqual((result.status, result.reason_code), ("rejected", "formal_base_required"))
        self.assertEqual(self.terminus.calls, [])

    def test_duplicate_submission_or_proposal_identity_returns_conflict(self):
        self.submit()
        duplicate_submission=self.submit(change_set(submission_id="submission-1",proposal_id="proposal-2"),"key-2")
        duplicate_proposal=self.submit(change_set(submission_id="submission-2",proposal_id="proposal-1"),"key-3")
        self.assertEqual(duplicate_submission.reason_code,"identity_conflict")
        self.assertEqual(duplicate_proposal.reason_code,"identity_conflict")
        self.assertEqual(len(self.terminus.calls),1)
