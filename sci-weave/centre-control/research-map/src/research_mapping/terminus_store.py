from __future__ import annotations

import base64
import hashlib
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from urllib.parse import quote

from . import errors
from .canonical import canonical_json
from .candidate_domain import CandidateSnapshotResult
from .domain import SNAPSHOT_CONFIRMED, SnapshotRead

Opener = Callable[[str, dict[str, str], float], tuple[int, Mapping[str, str], bytes]]
RequestOpener = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, Mapping[str, str], bytes]]


class CandidateSnapshotStore(Protocol):
    """Candidate write seam; unknown outcomes must never be treated as success."""

    def create_candidate_snapshot(
        self, domain_id: str, base_commit_ref: str, canonical_snapshot: str,
        idempotency_key: str,
    ) -> CandidateSnapshotResult: ...


def _normalize_set_fields(document):
    """Return a copy of ``document`` with list-valued (Set) fields sorted.

    TerminusDB stores ``@type: Set`` fields as unordered sets and returns their
    members in a canonical (sorted) order. A candidate submitted with a Set in a
    different order is the same document, so the read-back comparison must not
    depend on member order. Normalizing both sides keeps reconciliation
    order-independent (otherwise any unsorted Set yields a false
    ``store_result_unknown``).
    """
    if not isinstance(document, dict):
        return document
    normalized = dict(document)
    for key, value in list(normalized.items()):
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            normalized[key] = sorted(value)
        elif value is None:
            # TerminusDB omits an empty ``@type: Set`` field entirely from the
            # read-back, so an optional Set submitted as ``[]`` (or omitted) is
            # returned as ``None`` or absent. Treating ``None`` as the empty
            # list keeps ``_contains_documents`` from reporting a false
            # ``store_result_unknown`` for every node that has no executors or
            # every edge without optional fields. A non-empty value never
            # collapses to empty here, so real differences still show.
            normalized[key] = []
    return normalized


# 创世标记要真正落成一次提交，而 TerminusDB 12.0.8 对空写入不产生提交。
# 往 schema 图写一个标记类可以生成带 author/message 的提交，同时 instance 图保持为空，
# 这样 read_exact_snapshot 读到的仍是空快照。
_FORMAL_BOOTSTRAP_MARKER_CLASS = {
    "@type": "Class",
    "@id": "SciweaveFormalBootstrap",
    "@key": {"@type": "Lexical", "@fields": ["id"]},
    "id": "xsd:string",
}


# Candidate instance documents (@type TaskNode / DependencyEdge) must have their
# classes declared in the branch schema graph before the instance write, or
# TerminusDB 12.0.8 rejects them with api:SchemaCheckFailure
# (ascribed_type_does_not_exist) once the schema graph holds any class. This
# mirrors research-wiki's _WIKI_REVISION_SCHEMA approach. The formal bootstrap
# marker class (SciweaveFormalBootstrap) is what first makes the schema graph
# non-empty, so candidate writes always need these declared.
_TASK_NODE_SCHEMA = {
    "@type": "Class",
    "@id": "TaskNode",
    "@key": {"@type": "Lexical", "@fields": ["version_id"]},
    "mapping_domain_id": "xsd:string",
    "logical_id": "xsd:string",
    "version_id": "xsd:string",
    "title": "xsd:string",
    "objective": "xsd:string",
    "scope": "xsd:string",
    "acceptance_criteria": {"@type": "Set", "@class": "xsd:string"},
    "expected_outputs": {"@type": "Set", "@class": "xsd:string"},
    "required_evidence": {"@type": "Set", "@class": "xsd:string"},
    "executor_refs": {"@type": "Set", "@class": "xsd:string"},
    "task_owner_id": "xsd:string",
    "lifecycle_state": "xsd:string",
    "proposal_id": {"@type": "Optional", "@class": "xsd:string"},
    "base_formal_revision_id": {"@type": "Optional", "@class": "xsd:string"},
    "created_by": "xsd:string",
    "created_at": "xsd:string",
}

# source_node_version_ref / target_node_version_ref are inline NodeRef objects.
# Declaring NodeRef as its own Class makes TerminusDB rewrite them into top-level
# documents plus string references, breaking the exact read-back comparison.
# sys:JSON keeps them as opaque inline objects that round-trip unchanged.
_DEPENDENCY_EDGE_SCHEMA = {
    "@type": "Class",
    "@id": "DependencyEdge",
    "@key": {"@type": "Lexical", "@fields": ["version_id"]},
    "mapping_domain_id": "xsd:string",
    "logical_id": "xsd:string",
    "version_id": "xsd:string",
    "source_node_version_ref": "sys:JSON",
    "target_node_version_ref": "sys:JSON",
    "dependency_kind": "xsd:string",
    "required_outputs": {"@type": "Optional", "@class": "xsd:string"},
    "blocks_until": {"@type": "Optional", "@class": "xsd:string"},
    "activation_condition": {"@type": "Optional", "@class": "xsd:string"},
    "alternative_group_id": {"@type": "Optional", "@class": "xsd:string"},
    "lifecycle_state": "xsd:string",
    "proposal_id": {"@type": "Optional", "@class": "xsd:string"},
    "base_formal_revision_id": {"@type": "Optional", "@class": "xsd:string"},
    "created_by": "xsd:string",
    "created_at": "xsd:string",
}

_CANDIDATE_SCHEMA_CLASSES = [_TASK_NODE_SCHEMA, _DEPENDENCY_EDGE_SCHEMA]


def _documents_equal(stored, submitted):
    """Compare one stored document against the submitted one.

    TerminusDB omits an empty ``@type: Set`` field from the read-back entirely,
    so a submitted ``executor_refs: []`` (or any optional Set given as ``[]``)
    comes back as a missing key. Treating a missing key that the other side
    holds as an empty list as equal avoids a false ``store_result_unknown`` on
    every document that leaves an optional Set empty. Normalising away such
    empty Sets on both sides keeps the comparison order- and presence-robust.
    """
    if not isinstance(stored, dict) or not isinstance(submitted, dict):
        return False
    a = _normalize_set_fields(stored)
    b = _normalize_set_fields(submitted)
    for key in set(a) | set(b):
        av = a.get(key)
        bv = b.get(key)
        # A field present as an empty list on either side and missing (or None)
        # on the other is the same empty Set after TerminusDB's round-trip.
        if av in (None, []) and bv in (None, []):
            continue
        if av != bv:
            return False
    return True


def _contains_documents(actual, expected):
    """Confirm every submitted document exists unchanged in the exact commit."""
    by_id = {document.get("@id"): document for document in actual if isinstance(document, dict)}
    return all(
        isinstance(document.get("@id"), str)
        and _documents_equal(by_id.get(document["@id"]), document)
        for document in expected
    )


class ExactSnapshotStore(Protocol):
    """Boundary for reading one exact formal snapshot and its branch head."""

    def current_branch_head(self, store_id: str, database: str, branch_id: str) -> str | None: ...

    def read_exact_snapshot(
        self, store_id: str, database: str, branch_id: str, commit_hash: str
    ) -> SnapshotRead: ...


class TerminusDBStore:
    """TerminusDB 12.0.8 adapter for exact reads and isolated candidate writes."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        remote: str = "local",
        timeout: float = 10.0,
        opener: Opener | None = None,
        request_opener: RequestOpener | None = None,
        store_id: str | None = None,
        database: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.remote = remote
        self.timeout = timeout
        self._opener = opener or _urllib_opener
        self._request_opener = request_opener or _urllib_request_opener
        self.store_id = store_id
        self.database = database
        self._authorization = _resolve_authorization(token, username, password)

    def create_candidate_snapshot(
        self, domain_id: str, base_commit_ref: str, canonical_snapshot: str,
        idempotency_key: str,
    ) -> CandidateSnapshotResult:
        """Create or reconcile a candidate branch and its immutable commit.

        Branches are deterministic per idempotency key. An existing branch is
        only resumed at the exact base commit; any other head must carry this
        operation's marker and match the exact stored documents to reconcile.
        """
        if not self.store_id or not self.database or not idempotency_key or not base_commit_ref:
            return CandidateSnapshotResult("failed", reason_code="candidate_store_not_configured")
        try:
            documents = json.loads(canonical_snapshot)
            if not isinstance(documents, list) or not all(isinstance(doc, dict) for doc in documents):
                return CandidateSnapshotResult("failed", reason_code="invalid_candidate_snapshot")
        except (TypeError, json.JSONDecodeError):
            return CandidateSnapshotResult("failed", reason_code="invalid_candidate_snapshot")

        digest = hashlib.sha256(canonical_json(documents).encode("utf-8")).hexdigest()
        operation_id = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        branch = f"candidate-{operation_id}"
        marker = f"sciweave-candidate:{operation_id}:{domain_id}:{base_commit_ref}:{digest}"
        try:
            branches = self._branches()
            if branches is None:
                return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)
            branch_existed = branch in branches
            branch_created = False
            if not branch_existed:
                try:
                    status, _, _ = self._request(
                        "POST", self._branch_url(branch), json.dumps({
                            "origin": f"{quote(self.store_id, safe='')}/{quote(self.database, safe='')}/{quote(self.remote, safe='')}/branch/main"
                        }, separators=(",", ":")).encode()
                    )
                except (OSError, TimeoutError, urllib.error.URLError):
                    return self._reconcile_if_present(branch, marker, documents, digest)
                if not 200 <= status < 300:
                    if status in (409, 422) or status >= 500:
                        return self._reconcile_if_present(branch, marker, documents, digest)
                    return CandidateSnapshotResult("failed", reason_code="store_rejected")
                else:
                    branch_created = True
                if branch_created:
                    status, _, _ = self._request(
                        "POST", self._reset_url(branch), json.dumps({
                            "commit_descriptor": self._commit_descriptor(base_commit_ref)
                        }, separators=(",", ":")).encode()
                    )
                    if not 200 <= status < 300:
                        return CandidateSnapshotResult(
                            "unknown" if status >= 500 else "failed",
                            reason_code=errors.STORE_RESULT_UNKNOWN if status >= 500 else "store_rejected",
                        )

            current = self._head(branch)
            if current is None:
                return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)
            if current.get("identifier") != base_commit_ref:
                return self._reconcile(branch, marker, documents, digest, head=current)
            if branch_existed:
                # A branch at the requested base is not proof that this
                # operation owns it; never append to a pre-existing branch.
                return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)

            # 先把 TaskNode / DependencyEdge 类声明进该分支的 schema 图；否则在
            # schema 图非空时，TerminusDB 会以 ascribed_type_does_not_exist 拒绝实例写入，
            # 服务把它折成 store_rejected（实测 12.0.8）。声明幂等，重复调用安全。
            self._declare_candidate_schema(branch, marker)

            headers = {"Content-Type": "application/json"}
            if self._authorization:
                headers["Authorization"] = self._authorization
            url = self._branch_document_url(branch) + "?author=sciweave&message=" + quote(marker, safe="")
            status, response_headers, body = self._request_opener(
                "POST", url, headers, canonical_snapshot.encode("utf-8"), self.timeout
            )
            if not 200 <= status < 300:
                # A candidate branch is reset to base, so re-declaring an existing
                # node (required when an edge's endpoint is a base node -- the
                # validator insists every edge endpoint be declared in the change
                # set) makes the batch POST fail with DocumentIdAlreadyExists.
                # TerminusDB has no single upsert verb: POST creates only, PUT
                # replaces only. Fall back to a per-document upsert: PUT then, on
                # DocumentNotFound, POST. (ai4-su27)
                if status == 400 and b"DocumentIdAlreadyExists" in (body or b""):
                    fallback = self._upsert_documents(branch, documents, marker, headers)
                    if fallback is not None:
                        return self._reconcile(branch, marker, documents, digest, fallback)
                if status >= 500:
                    return self._reconcile(branch, marker, documents, digest)
                return CandidateSnapshotResult("failed", reason_code="store_rejected")
            return self._reconcile(branch, marker, documents, digest, response_headers)
        except (OSError, TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            return self._reconcile(branch, marker, documents, digest)

    def _upsert_documents(self, branch, documents, marker, headers):
        """Per-document insert-or-replace on the candidate branch.

        TerminusDB's document API has no insert-or-replace verb: POST inserts
        (fails DocumentIdAlreadyExists if the id exists) and PUT replaces (fails
        DocumentNotFound if the id is absent). A candidate branch is reset to
        base, so re-declared base nodes already exist while result nodes do not.
        Try PUT first, fall back to POST for genuinely new documents. Each write
        uses the same commit ``marker`` so the branch head message stays the
        marker the caller reconciles against.
        """
        base_url = self._branch_document_url(branch)
        for document in documents:
            encoded = json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")
            url = base_url + "?author=sciweave&message=" + quote(marker, safe="")
            status, _, _ = self._request_opener("PUT", url, headers, encoded, self.timeout)
            if 200 <= status < 300:
                continue
            if status == 404:
                status, _, _ = self._request_opener("POST", url, headers, encoded, self.timeout)
                if 200 <= status < 300:
                    continue
            return None
        return {}

    def _reconcile_if_present(self, branch, marker, documents, digest):
        branches = self._branches()
        if branches is None or branch not in branches:
            return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)
        head = self._head(branch)
        if head is None:
            return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)
        return self._reconcile(branch, marker, documents, digest, head=head)

    def _reconcile(self, branch, marker, documents, digest, response_headers=None, head=None):
        try:
            head = head if head is not None else self._head(branch)
            if head is None or head.get("message") != marker or head.get("author") != "sciweave":
                return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)
            commit = head.get("identifier")
            if not isinstance(commit, str) or not commit:
                return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)
            read_status, headers, body = self._request(
                "GET", self._document_commit_url(self.store_id, self.database, commit)
            )
            if not 200 <= read_status < 300:
                return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)
            normalized = {str(k).lower(): str(v) for k, v in headers.items()}
            if normalized.get("terminusdb-data-version") != f"commit:{commit}" or "json" not in normalized.get("content-type", "").lower():
                return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)
            actual = json.loads(body.decode("utf-8"))
            if not isinstance(actual, list) or not _contains_documents(actual, documents):
                return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)
            if hashlib.sha256(canonical_json(documents).encode("utf-8")).hexdigest() != digest:
                return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)
            return CandidateSnapshotResult("confirmed", self.store_id, branch, commit)
        except (OSError, TimeoutError, urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
            return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)

    def _branches(self):
        status, _, body = self._request("GET", self._database_url() + "?branches=true")
        if not 200 <= status < 300:
            return None
        try:
            payload = json.loads(body.decode("utf-8"))
            branches = payload.get("branches") if isinstance(payload, dict) else None
            return set(branches) if isinstance(branches, list) and all(isinstance(x, str) for x in branches) else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _head(self, branch):
        status, _, body = self._request("GET", self._log_url(branch) + "?count=1")
        if not 200 <= status < 300:
            return None
        try:
            entries = json.loads(body.decode("utf-8"))
            return entries[0] if isinstance(entries, list) and entries and isinstance(entries[0], dict) else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _request(self, method, url, body=None):
        headers = {"Accept": "application/json"}
        if self._authorization:
            headers["Authorization"] = self._authorization
        if body is not None:
            headers["Content-Type"] = "application/json"
        return self._request_opener(method, url, headers, body, self.timeout)

    def _database_url(self):
        return f"{self.base_url}/api/db/{quote(self.store_id, safe='')}/{quote(self.database, safe='')}"

    def _branch_url(self, branch):
        return f"{self.base_url}/api/branch/{quote(self.store_id, safe='')}/{quote(self.database, safe='')}/{quote(self.remote, safe='')}/branch/{quote(branch, safe='')}"

    def _reset_url(self, branch):
        return f"{self.base_url}/api/reset/{quote(self.store_id, safe='')}/{quote(self.database, safe='')}/{quote(self.remote, safe='')}/branch/{quote(branch, safe='')}"

    def _branch_document_url(self, branch):
        return f"{self.base_url}/api/document/{quote(self.store_id, safe='')}/{quote(self.database, safe='')}/{quote(self.remote, safe='')}/branch/{quote(branch, safe='')}"

    def _log_url(self, branch):
        return f"{self.base_url}/api/log/{quote(self.store_id, safe='')}/{quote(self.database, safe='')}/{quote(self.remote, safe='')}/branch/{quote(branch, safe='')}"

    def _commit_descriptor(self, commit):
        return f"{quote(self.store_id, safe='')}/{quote(self.database, safe='')}/{quote(self.remote, safe='')}/commit/{quote(commit, safe='')}"

    def current_branch_head(self, store_id: str, database: str, branch_id: str) -> str | None:
        """Return the current immutable commit identifier for a branch, if confirmed."""
        if not store_id or not database or not branch_id:
            return None
        try:
            status, _, body = self._request(
                "GET", self._log_url_for(store_id, database, branch_id) + "?count=1"
            )
            if not 200 <= status < 300:
                return None
            entries = json.loads(body.decode("utf-8"))
            if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
                return None
            identifier = entries[0].get("identifier")
            return identifier if isinstance(identifier, str) and identifier else None
        except (OSError, TimeoutError, urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _log_url_for(self, store_id, database, branch):
        return (f"{self.base_url}/api/log/{quote(store_id, safe='')}/{quote(database, safe='')}/"
                f"{quote(self.remote, safe='')}/branch/{quote(branch, safe='')}")

    def ensure_empty_formal_snapshot(
        self, domain_id: str, *, branch_id: str | None = None, operation_id: str | None = None
    ) -> SnapshotRead:
        """Create, or reconcile, the deterministic empty formal snapshot for a domain.

        The branch and commit marker are domain-scoped, so a retry never creates a
        second logical bootstrap snapshot.  A branch that exists without our
        marker is treated as an unknown conflict and is never overwritten.
        """
        if not self.store_id or not self.database or not domain_id:
            return SnapshotRead.unavailable("formal_store_not_configured")
        identity = operation_id or hashlib.sha256(
            f"research-map:formal-bootstrap:{domain_id}".encode("utf-8")
        ).hexdigest()
        branch = branch_id or f"formal-{identity[:32]}"
        marker = f"sciweave-formal-bootstrap:{identity}:{domain_id}"
        try:
            branches = self._branches()
            if branches is None:
                return SnapshotRead.unavailable(errors.STORE_UNAVAILABLE)
            branch_created = False
            if branch not in branches:
                status, _, _ = self._request(
                    "POST", self._branch_url(branch), json.dumps({
                        "origin": f"{quote(self.store_id, safe='')}/{quote(self.database, safe='')}/"
                        f"{quote(self.remote, safe='')}/branch/main"
                    }, separators=(",", ":")).encode()
                )
                if not 200 <= status < 300:
                    branches = self._branches()
                    if branches is None or branch not in branches:
                        return SnapshotRead.unavailable(
                            errors.STORE_RESULT_UNKNOWN if status >= 500 else "formal_branch_conflict"
                        )
                else:
                    branch_created = True
            head = None if branch_created else self._head(branch)
            if not branch_created:
                if head is None:
                    return SnapshotRead.unavailable(errors.STORE_RESULT_UNKNOWN)
                if head.get("message") != marker or head.get("author") != "sciweave":
                    # 分支在、但没有我们的标记提交：只有在 instance 图为空、没有数据可丢的情况下
                    # 才认领它（补齐标记提交）；否则仍是真冲突。历史上写空数组没能生成提交，
                    # 就会留下这种"空分支无标记"的状态。
                    adopted = self._adopt_markerless_empty_branch(branch, marker)
                    if adopted is None:
                        return SnapshotRead.unavailable("formal_branch_conflict")
                    head = adopted
                commit = head.get("identifier")
                if not isinstance(commit, str) or not commit:
                    return SnapshotRead.unavailable(errors.STORE_RESULT_UNKNOWN)
                snapshot = self.read_exact_snapshot(self.store_id, self.database, branch, commit)
                if snapshot.status != SNAPSHOT_CONFIRMED or snapshot.documents:
                    return snapshot if snapshot.status != SNAPSHOT_CONFIRMED else SnapshotRead.unavailable("formal_snapshot_not_empty")
                return snapshot
            status, response_headers, _ = self._request_opener(
                "POST",
                self._branch_document_url(branch)
                + "?author=sciweave&message=" + quote(marker, safe="")
                + "&graph_type=schema",
                {"Accept": "application/json", "Content-Type": "application/json", **({"Authorization": self._authorization} if self._authorization else {})},
                json.dumps([_FORMAL_BOOTSTRAP_MARKER_CLASS], separators=(",", ":")).encode(),
                self.timeout,
            )
            if not 200 <= status < 300:
                return SnapshotRead.unavailable(errors.STORE_RESULT_UNKNOWN if status >= 500 else "formal_store_rejected")
            head = self._head(branch)
            if head is None or head.get("message") != marker or head.get("author") != "sciweave":
                return SnapshotRead.unavailable(errors.STORE_RESULT_UNKNOWN)
            commit = head.get("identifier")
            if not isinstance(commit, str) or not commit:
                return SnapshotRead.unavailable(errors.STORE_RESULT_UNKNOWN)
            snapshot = self.read_exact_snapshot(self.store_id, self.database, branch, commit)
            if snapshot.status != SNAPSHOT_CONFIRMED or snapshot.documents:
                return snapshot if snapshot.status != SNAPSHOT_CONFIRMED else SnapshotRead.unavailable("formal_snapshot_not_empty")
            return snapshot
        except (OSError, TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            return SnapshotRead.unavailable(errors.STORE_RESULT_UNKNOWN)

    def _adopt_markerless_empty_branch(self, branch, marker):
        """Claim an existing branch that has no marker commit.

        Only safe when the instance graph is empty: nothing can be lost. This
        recovers the state left behind by the old bootstrap, which wrote an
        empty document list (TerminusDB 12.0.8 creates no commit for that) and
        then failed its own marker check.
        """
        head = self._head(branch)
        if head is None:
            return None
        commit = head.get("identifier")
        if not isinstance(commit, str) or not commit:
            return None
        current = self.read_exact_snapshot(self.store_id, self.database, branch, commit)
        if current.status != SNAPSHOT_CONFIRMED or current.documents:
            return None
        status, _, _ = self._request_opener(
            "POST",
            self._branch_document_url(branch)
            + "?author=sciweave&message=" + quote(marker, safe="")
            + "&graph_type=schema",
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                **({"Authorization": self._authorization} if self._authorization else {}),
            },
            json.dumps([_FORMAL_BOOTSTRAP_MARKER_CLASS], separators=(",", ":")).encode(),
            self.timeout,
        )
        if not 200 <= status < 300:
            return None
        new_head = self._head(branch)
        if (
            new_head is None
            or new_head.get("message") != marker
            or new_head.get("author") != "sciweave"
        ):
            return None
        return new_head

    def _declare_candidate_schema(self, branch, marker):
        """Declare the candidate document classes in the branch schema graph.

        Idempotent: TerminusDB accepts re-declaring an identical class with 200.
        Non-fatal on failure — the subsequent instance write is still attempted
        and will surface a real store_rejected if the schema could not be set.
        """
        try:
            self._request(
                "POST",
                self._branch_document_url(branch)
                + "?author=sciweave&message=" + quote(marker + ":schema", safe="")
                + "&graph_type=schema",
                json.dumps(_CANDIDATE_SCHEMA_CLASSES, ensure_ascii=False,
                           separators=(",", ":")).encode("utf-8"),
            )
        except (OSError, TimeoutError, urllib.error.URLError, ValueError):
            return

    def create_formal_snapshot(
        self, store_id: str, database: str, branch_id: str, commit_hash: str, operation_id: str
    ) -> SnapshotRead:
        """Promote by immutable reference: the locked candidate Commit is the formal graph snapshot.

        SQLite activation is the only publication switch. Reusing the exact commit avoids
        copying or mutating graph documents and makes retries idempotent.
        """
        if not operation_id:
            return SnapshotRead.unavailable("formalization_operation_missing")
        return self.read_exact_snapshot(store_id, database, branch_id, commit_hash)

    def read_exact_snapshot(
        self, store_id: str, database: str, branch_id: str, commit_hash: str
    ) -> SnapshotRead:
        url = self._document_commit_url(store_id, database, commit_hash)
        headers = {
            "Accept": "application/json",
            "TerminusDB-Data-Version": f"commit:{commit_hash}",
        }
        if self._authorization:
            headers["Authorization"] = self._authorization

        try:
            status, response_headers, body = self._opener(url, headers, self.timeout)
        except (OSError, TimeoutError, urllib.error.URLError):
            return SnapshotRead.unavailable(errors.STORE_UNAVAILABLE)

        if status == 404:
            return SnapshotRead.missing()
        if status < 200 or status >= 300:
            return SnapshotRead.unavailable(errors.STORE_UNAVAILABLE)

        normalized = {str(key).lower(): str(value) for key, value in response_headers.items()}
        if "json" not in normalized.get("content-type", "").lower():
            return SnapshotRead.unavailable(errors.UNEXPECTED_CONTENT_TYPE)
        data_version = normalized.get("terminusdb-data-version")
        if data_version is None:
            return SnapshotRead.unavailable(errors.DATA_VERSION_MISSING)
        if data_version != f"commit:{commit_hash}":
            return SnapshotRead.unavailable(errors.DATA_VERSION_MISMATCH)
        try:
            payload: Any = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return SnapshotRead.unavailable(errors.UNEXPECTED_PAYLOAD)
        if not isinstance(payload, list) or not all(isinstance(document, dict) for document in payload):
            return SnapshotRead.unavailable(errors.UNEXPECTED_PAYLOAD)
        return SnapshotRead.confirmed(
            store_id=store_id, database=database, branch_id=branch_id,
            commit_hash=commit_hash, documents=payload,
        )

    def _document_commit_url(self, store_id: str, database: str, commit_hash: str) -> str:
        segments = {
            "store": quote(store_id, safe=""), "database": quote(database, safe=""),
            "remote": quote(self.remote, safe=""), "commit": quote(commit_hash, safe=""),
        }
        return (f"{self.base_url}/api/document/{segments['store']}/{segments['database']}/"
                f"{segments['remote']}/commit/{segments['commit']}?as_list=true&graph_type=instance")


def _resolve_authorization(token: str | None, username: str | None, password: str | None) -> str | None:
    """Resolve either Bearer or HTTP Basic authentication."""
    if token and (username or password):
        raise ValueError("configure either a TerminusDB token or basic credentials, not both")
    if username or password:
        if not username or not password:
            raise ValueError("TerminusDB basic credentials need both username and password")
        credentials = f"{username}:{password}".encode("utf-8")
        return "Basic " + base64.b64encode(credentials).decode("ascii")
    if token:
        return f"Bearer {token}"
    return None


def _urllib_opener(url: str, headers: dict[str, str], timeout: float):
    return _urllib_request_opener("GET", url, headers, None, timeout)


def _urllib_request_opener(method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float):
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {}), error.read()
