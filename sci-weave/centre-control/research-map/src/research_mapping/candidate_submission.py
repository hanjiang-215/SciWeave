from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from typing import Any, Protocol

from .candidate_domain import CandidateSnapshotResult, CandidateSubmissionResult, utc_now
from .canonical import canonical_json, sha256_json

# Stable reason codes for candidate submission validation (write-time gates).
# These mirror the mechanical checks moved to the domain MCP in ai4-eex0:
# format/reference/cycle are write-time rejections; base staleness is a
# prereview fact, not a write-time rejection.
FORMAL_BASE_REQUIRED = "formal_base_required"
BASE_REVISION_MISSING = "base_revision_missing"


class CandidateSnapshotStore(Protocol):
    def create_candidate_snapshot(
        self, domain_id: str, base_commit_ref: str, canonical_snapshot: str,
        idempotency_key: str,
    ) -> CandidateSnapshotResult: ...


class _StaleFormalBase(Exception):
    pass


class MappingCandidateService:
    def __init__(self, sqlite_store, terminus_store: CandidateSnapshotStore, *, terminus_database: str):
        self._sqlite = sqlite_store
        self._terminus = terminus_store
        self._database = terminus_database

    def submit(self, change_set: dict[str, Any], idempotency_key: str) -> CandidateSubmissionResult:
        change_set = _assign_versioned_document_ids(change_set)
        identity = _required(change_set, "submission_id")
        domain = _required(change_set, "mapping_domain_id")
        submitter = _required(change_set, "submitter_id")
        base = change_set.get("base_formal_revision_id")
        digest = sha256_json(change_set)
        previous = None
        with self._sqlite.connection() as connection:
            previous = connection.execute(
                "SELECT * FROM mapping_submission WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if previous:
                identity_matches = (
                    previous["mapping_domain_id"] == domain
                    and previous["submitter_id"] == submitter
                    and previous["submission_id"] == identity
                    and previous["content_digest"] == digest
                )
                if not identity_matches:
                    return _result("rejected", "idempotency_conflict", identity)
                commit = connection.execute(
                    "SELECT * FROM mapping_candidate_commit WHERE proposal_id = ?", (previous["proposal_id"],)
                ).fetchone()
                if commit:
                    return _from_rows(previous, commit)
                if previous["status"] == "failed":
                    return _result("failed", "store_rejected", identity, previous["proposal_id"])
                # pending/result_unknown is reconciled through the store using
                # this original key, base and canonical payload below.
            else:
                proposal_id = _required(change_set, "proposal_id")
                collision = connection.execute(
                    "SELECT submission_id, proposal_id FROM mapping_submission "
                    "WHERE submission_id = ? OR proposal_id = ? LIMIT 1",
                    (identity, proposal_id),
                ).fetchone()
                if collision:
                    return _result("rejected", "identity_conflict", identity, proposal_id)
                connection.execute("""INSERT INTO mapping_submission
                    (submission_id,mapping_domain_id,submitter_id,base_formal_revision_id,idempotency_key,
                     content_digest,proposal_id,submitted_at,status)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (identity, domain, submitter, base, idempotency_key, digest,
                     proposal_id, utc_now(), "pending"))
                connection.commit()

        reconciling = previous is not None and previous["status"] in {"pending", "result_unknown"}
        if reconciling:
            # Reconciliation must use the original stored identity. A missing
            # SQLite base field may be recovered from the same retry payload,
            # but it is never replaced with a guessed commit.
            proposal_id = previous["proposal_id"]
            # A retry payload with a matching content digest carries the
            # original base identity; otherwise fall back to the stored field.
            base = base or previous["base_formal_revision_id"]
            try:
                candidate_documents = canonical_json(change_set["nodes"] + change_set["edges"])
            except (KeyError, TypeError):
                return _result("result_unknown", "store_result_unknown", identity, proposal_id)
            if base is None:
                base_commit, store_id = "", ""
            else:
                revision = self._sqlite.get_formal_revision(base)
                if revision is None or revision.mapping_domain_id != domain:
                    return _result("result_unknown", "store_result_unknown", identity, proposal_id)
                base_commit, store_id = revision.formal_commit_hash, revision.terminus_store_id
        else:
            reason = _validate(change_set)
            if reason:
                self._set_submission(identity, "rejected")
                return _result("rejected", reason, identity)
            if base is None:
                self._set_submission(identity, "rejected")
                return _result("rejected", FORMAL_BASE_REQUIRED, identity)
            revision = self._sqlite.get_formal_revision(base)
            if revision is None or revision.mapping_domain_id != domain:
                self._set_submission(identity, "rejected")
                return _result("rejected", BASE_REVISION_MISSING, identity)
            base_commit, store_id = revision.formal_commit_hash, revision.terminus_store_id
            candidate_documents = canonical_json(change_set["nodes"] + change_set["edges"])

        snapshot_digest = sha256_json(change_set["nodes"] + change_set["edges"])
        operation_identity = sha256_json({
            "idempotency_key": idempotency_key,
            "submission_id": identity,
            "submitter_id": submitter,
            "mapping_domain_id": domain,
            "base_formal_revision_id": base,
            "candidate_snapshot_digest": snapshot_digest,
        })
        try:
            raw = self._terminus.create_candidate_snapshot(
                domain, base_commit, candidate_documents, operation_identity
            )
            outcome = raw if isinstance(raw, CandidateSnapshotResult) else CandidateSnapshotResult(**raw)
        except Exception:
            outcome = CandidateSnapshotResult("unknown", reason_code="store_result_unknown")
        if outcome.status == "unknown":
            return _result("result_unknown", "store_result_unknown", identity, change_set.get("proposal_id"))
        if outcome.status != "confirmed" or not all((outcome.store_id, outcome.branch_id, outcome.commit_hash)):
            self._set_submission(identity, "failed")
            return _result("failed", outcome.reason_code or "store_rejected", identity, change_set.get("proposal_id"))
        if store_id and outcome.store_id != store_id:
            return _result("result_unknown", "store_result_unknown", identity, change_set.get("proposal_id"))
        if self._sqlite.get_formal_revision(base) is None:
            return _result("rejected", BASE_REVISION_MISSING, identity, change_set.get("proposal_id"))
        try:
            self._persist(
                change_set, idempotency_key, digest, snapshot_digest, outcome, expected_base=base
            )
        except _StaleFormalBase:
            return _result("rejected", BASE_REVISION_MISSING, identity, change_set.get("proposal_id"))
        except sqlite3.Error:
            return _result("result_unknown", "result_unknown", identity, change_set.get("proposal_id"))
        with self._sqlite.connection() as connection:
            submission = connection.execute("SELECT * FROM mapping_submission WHERE submission_id=?", (identity,)).fetchone()
            commit = connection.execute("SELECT * FROM mapping_candidate_commit WHERE proposal_id=?", (submission["proposal_id"],)).fetchone()
        return _from_rows(submission, commit)

    def _set_submission(self, submission_id: str, status: str) -> None:
        with self._sqlite.connection() as connection:
            connection.execute("UPDATE mapping_submission SET status=? WHERE submission_id=?", (status, submission_id))
            connection.commit()

    def _persist(self, cs, key, digest, snapshot_digest, outcome, *, expected_base):
        now = utc_now()
        proposal = cs["proposal_id"]
        candidate_id = "candidate-commit-" + hashlib.sha256(key.encode()).hexdigest()[:16]
        event_id = "audit-" + hashlib.sha256((key + ":candidate").encode()).hexdigest()[:16]
        with self._sqlite.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            base_row = connection.execute(
                "SELECT formal_revision_id FROM formal_mapping_revision "
                "WHERE formal_revision_id=? AND mapping_domain_id=?",
                (expected_base, cs["mapping_domain_id"]),
            ).fetchone()
            if base_row is None:
                raise _StaleFormalBase()
            prior = connection.execute("SELECT * FROM mapping_candidate_commit WHERE proposal_id=?", (proposal,)).fetchone()
            if prior:
                if (
                    prior["candidate_snapshot_digest"] != snapshot_digest
                    or prior["commit_hash"] != outcome.commit_hash
                ):
                    raise sqlite3.IntegrityError("candidate identity conflict")
                return
            connection.execute("""
                INSERT INTO mapping_proposal
                (proposal_id,mapping_domain_id,base_formal_revision_id,candidate_store_id,
                 candidate_branch_id,status,created_by,created_at)
                VALUES (?,?,?,?,?,?,?,?)
            """,
                (proposal, cs["mapping_domain_id"], cs.get("base_formal_revision_id"), outcome.store_id,
                 outcome.branch_id, "candidate", cs["submitter_id"], now))
            connection.execute("""
                INSERT INTO mapping_candidate_commit
                (candidate_commit_id,mapping_domain_id,proposal_id,terminus_store_id,branch_id,
                 commit_hash,base_formal_revision_id,content_digest,candidate_snapshot_digest,
                 created_by,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
                (candidate_id, cs["mapping_domain_id"], proposal, outcome.store_id, outcome.branch_id,
                 outcome.commit_hash, cs.get("base_formal_revision_id"), digest,
                 snapshot_digest, cs["submitter_id"], now))
            connection.execute("UPDATE mapping_submission SET status='candidate_created' WHERE idempotency_key=?", (key,))
            connection.execute("INSERT INTO mapping_audit_event VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (event_id, cs["mapping_domain_id"], cs["submitter_id"], "candidate_created", "MappingProposal",
                 proposal, "confirmed", now, cs["submission_id"], proposal, candidate_id))
            connection.commit()


def _assign_versioned_document_ids(change_set: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(change_set)
    for object_type, collection in (("TaskNode", "nodes"), ("DependencyEdge", "edges")):
        documents = normalized.get(collection)
        if not isinstance(documents, list):
            continue
        for document in documents:
            if not isinstance(document, dict):
                continue
            version_id = document.get("version_id")
            if not isinstance(version_id, str) or not version_id:
                continue
            expected_id = f"{object_type}/{version_id}"
            if "@id" not in document:
                document["@id"] = expected_id
    return normalized


def _required(value, key):
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{key} is required")
    return result


def _validate(cs):
    if not isinstance(cs.get("nodes"), list) or not isinstance(cs.get("edges"), list):
        return "invalid_change_set"
    domain = cs.get("mapping_domain_id")
    nodes = {}
    for node in cs["nodes"]:
        if not isinstance(node, dict) or node.get("@type") != "TaskNode":
            return "invalid_task_node"
        required = ("logical_id", "version_id", "title", "objective", "scope", "task_owner_id", "created_by", "created_at")
        if any(not isinstance(node.get(key), str) or not node[key].strip() for key in required):
            return "invalid_task_node"
        if node.get("@id") != f"TaskNode/{node['version_id']}":
            return "invalid_task_node_id"
        if any(not isinstance(node.get(key), list) or not node[key] for key in ("acceptance_criteria", "expected_outputs", "required_evidence")):
            return "invalid_task_node"
        if node.get("mapping_domain_id") != domain or node.get("lifecycle_state") != "candidate":
            return "invalid_task_node"
        if node.get("proposal_id") != cs.get("proposal_id") or node.get("base_formal_revision_id") != cs.get("base_formal_revision_id"):
            return "invalid_task_node"
        ref = (node["logical_id"], node["version_id"])
        if ref in nodes:
            return "invalid_task_node"
        nodes[ref] = node
    blocking = {}
    edge_identities = set()
    for edge in cs["edges"]:
        if not isinstance(edge, dict) or edge.get("@type") != "DependencyEdge":
            return "invalid_dependency_edge"
        required_edge = ("logical_id", "version_id", "mapping_domain_id", "dependency_kind",
                         "lifecycle_state", "created_by", "created_at")
        if any(not isinstance(edge.get(key), str) or not edge[key].strip() for key in required_edge):
            return "invalid_dependency_edge"
        if edge.get("@id") != f"DependencyEdge/{edge['version_id']}":
            return "invalid_dependency_edge_id"
        source, target = edge.get("source_node_version_ref"), edge.get("target_node_version_ref")
        if not isinstance(source, dict) or not isinstance(target, dict):
            return "invalid_dependency_edge"
        if any(not isinstance(ref.get(key), str) or not ref[key].strip()
               for ref in (source, target) for key in ("logical_id", "version_id")):
            return "invalid_dependency_edge"
        if source.get("mapping_domain_id", domain) != domain or target.get("mapping_domain_id", domain) != domain:
            return "invalid_dependency_edge"
        if (source.get("logical_id"), source.get("version_id")) not in nodes or (target.get("logical_id"), target.get("version_id")) not in nodes:
            return "missing_relation_target"
        source_ref = (source["logical_id"], source["version_id"])
        target_ref = (target["logical_id"], target["version_id"])
        if source_ref == target_ref:
            return "self_loop"
        if edge.get("mapping_domain_id") != domain or edge.get("lifecycle_state") != "candidate" or edge.get("proposal_id") != cs.get("proposal_id") or edge.get("base_formal_revision_id") != cs.get("base_formal_revision_id"):
            return "invalid_dependency_edge"
        if not isinstance(edge.get("proposal_id"), str) or not edge["proposal_id"].strip():
            return "invalid_dependency_edge"
        base_ref = edge.get("base_formal_revision_id")
        if not isinstance(base_ref, str) or not base_ref.strip():
            return "invalid_dependency_edge"
        edge_identity = (edge["logical_id"], edge["version_id"])
        if edge_identity in edge_identities:
            return "duplicate_dependency_edge"
        edge_identities.add(edge_identity)
        kind = edge.get("dependency_kind")
        if kind not in {"information", "blocking", "conditional", "alternative"}:
            return "invalid_dependency_edge"
        if kind == "blocking":
            if not edge.get("required_outputs") or not edge.get("blocks_until"):
                return "invalid_dependency_edge"
            blocking.setdefault(source_ref, []).append(target_ref)
        if kind in {"conditional", "alternative"} and not edge.get("activation_condition"):
            return "invalid_dependency_edge"
        if kind == "alternative" and not edge.get("alternative_group_id"):
            return "invalid_dependency_edge"
    visiting, visited = set(), set()
    def visit(vertex):
        if vertex in visiting:
            return True
        if vertex in visited:
            return False
        visiting.add(vertex)
        if any(visit(next_vertex) for next_vertex in blocking.get(vertex, [])):
            return True
        visiting.remove(vertex)
        visited.add(vertex)
        return False
    return "blocking_cycle" if any(visit(vertex) for vertex in blocking) else None


def _result(status, reason, submission, proposal=None):
    return CandidateSubmissionResult(status, reason, submission, proposal)


def _from_rows(submission, commit):
    snapshot_digest = commit["candidate_snapshot_digest"]
    if not snapshot_digest:
        return CandidateSubmissionResult(
            "result_unknown", "candidate_snapshot_unverified", submission["submission_id"],
            submission["proposal_id"],
        )
    return CandidateSubmissionResult("confirmed", "ok", submission["submission_id"], submission["proposal_id"],
        commit["candidate_commit_id"], commit["branch_id"], commit["commit_hash"], snapshot_digest)
