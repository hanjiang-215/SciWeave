from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Protocol

from .candidate_domain import CandidateSnapshotResult, CandidateSubmissionResult, utc_now
from .canonical import canonical_json, sha256_json


class CandidateSnapshotStore(Protocol):
    def create_candidate_snapshot(
        self, domain_id: str, base_commit_ref: str, canonical_snapshot: str,
        idempotency_key: str,
    ) -> CandidateSnapshotResult: ...


class MappingCandidateService:
    def __init__(self, sqlite_store, terminus_store: CandidateSnapshotStore, *, terminus_database: str):
        self._sqlite = sqlite_store
        self._terminus = terminus_store
        self._database = terminus_database

    def submit(self, change_set: dict[str, Any], idempotency_key: str) -> CandidateSubmissionResult:
        identity = _required(change_set, "submission_id")
        domain = _required(change_set, "mapping_domain_id")
        submitter = _required(change_set, "submitter_id")
        base = change_set.get("base_formal_revision_id")
        digest = sha256_json(change_set)
        with self._sqlite.connection() as connection:
            previous = connection.execute(
                "SELECT * FROM mapping_submission WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if previous:
                if (previous["mapping_domain_id"], previous["submitter_id"], previous["submission_id"],
                    previous["base_formal_revision_id"], previous["content_digest"]) != (domain, submitter, identity, base, digest):
                    return _result("rejected", "idempotency_conflict", identity)
                commit = connection.execute(
                    "SELECT * FROM mapping_candidate_commit WHERE proposal_id = ?", (previous["proposal_id"],)
                ).fetchone()
                if commit:
                    return _from_rows(previous, commit)
                if previous["status"] == "failed":
                    return _result("failed", "store_rejected", identity, previous["proposal_id"])
                if previous["status"] in {"pending", "result_unknown"}:
                    self._set_submission(identity, "result_unknown")
                    return _result("result_unknown", "store_result_unknown", identity, previous["proposal_id"])
            else:
                connection.execute("""INSERT INTO mapping_submission
                    (submission_id,mapping_domain_id,submitter_id,base_formal_revision_id,idempotency_key,
                     content_digest,proposal_id,submitted_at,status)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (identity, domain, submitter, base, idempotency_key, digest,
                     _required(change_set, "proposal_id"), utc_now(), "pending"))
                connection.commit()

        reason = _validate(change_set)
        if reason:
            self._set_submission(identity, "rejected")
            return _result("rejected", reason, identity)
        current = self._sqlite.get_current_formal_revision_id(domain)
        if base is None:
            if current is not None:
                self._set_submission(identity, "rejected")
                return _result("rejected", "stale_base", identity)
            base_commit = ""
            store_id = ""
        else:
            revision = self._sqlite.get_formal_revision(base)
            if current != base or revision is None or revision.mapping_domain_id != domain:
                self._set_submission(identity, "rejected")
                return _result("rejected", "stale_base", identity)
            base_commit, store_id = revision.formal_commit_hash, revision.terminus_store_id

        snapshot = canonical_json(change_set)
        try:
            raw = self._terminus.create_candidate_snapshot(domain, base_commit, snapshot, idempotency_key)
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
        try:
            self._persist(change_set, idempotency_key, digest, outcome)
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

    def _persist(self, cs, key, digest, outcome):
        now = utc_now()
        proposal = cs["proposal_id"]
        candidate_id = "candidate-commit-" + hashlib.sha256(key.encode()).hexdigest()[:16]
        event_id = "audit-" + hashlib.sha256((key + ":candidate").encode()).hexdigest()[:16]
        with self._sqlite.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute("SELECT * FROM mapping_candidate_commit WHERE proposal_id=?", (proposal,)).fetchone()
            if prior:
                if prior["content_digest"] != digest or prior["commit_hash"] != outcome.commit_hash:
                    raise sqlite3.IntegrityError("candidate identity conflict")
                return
            connection.execute("INSERT INTO mapping_proposal VALUES (?,?,?,?,?,?,?,?)",
                (proposal, cs["mapping_domain_id"], cs.get("base_formal_revision_id"), outcome.store_id,
                 outcome.branch_id, "candidate", cs["submitter_id"], now))
            connection.execute("INSERT INTO mapping_candidate_commit VALUES (?,?,?,?,?,?,?,?,?,?)",
                (candidate_id, cs["mapping_domain_id"], proposal, outcome.store_id, outcome.branch_id,
                 outcome.commit_hash, cs.get("base_formal_revision_id"), digest, cs["submitter_id"], now))
            connection.execute("UPDATE mapping_submission SET status='candidate_created' WHERE idempotency_key=?", (key,))
            connection.execute("INSERT INTO mapping_audit_event VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (event_id, cs["mapping_domain_id"], cs["submitter_id"], "candidate_created", "MappingProposal",
                 proposal, "confirmed", now, cs["submission_id"], proposal, candidate_id))
            connection.commit()


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
    for edge in cs["edges"]:
        if not isinstance(edge, dict) or edge.get("@type") != "DependencyEdge":
            return "invalid_dependency_edge"
        required_edge = ("logical_id", "version_id")
        if any(not isinstance(edge.get(key), str) or not edge[key].strip() for key in required_edge):
            return "invalid_dependency_edge"
        source, target = edge.get("source_node_version_ref"), edge.get("target_node_version_ref")
        if not isinstance(source, dict) or not isinstance(target, dict) or (source.get("logical_id"), source.get("version_id")) not in nodes or (target.get("logical_id"), target.get("version_id")) not in nodes:
            return "missing_relation_target"
        source_ref = (source["logical_id"], source["version_id"])
        target_ref = (target["logical_id"], target["version_id"])
        if source_ref == target_ref:
            return "self_loop"
        if edge.get("mapping_domain_id") != domain or edge.get("lifecycle_state") != "candidate" or edge.get("proposal_id") != cs.get("proposal_id") or edge.get("base_formal_revision_id") != cs.get("base_formal_revision_id"):
            return "invalid_dependency_edge"
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
    return CandidateSubmissionResult("confirmed", "ok", submission["submission_id"], submission["proposal_id"],
        commit["candidate_commit_id"], commit["branch_id"], commit["commit_hash"], commit["content_digest"])
