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
from .canonical import sha256_json
from .domain import ResourceVersionLocation, ResourceVersionRead, ResourceVersionSnapshot
from .formal_domain import WikiSnapshotRead

Opener = Callable[[str, dict[str, str], float], tuple[int, Mapping[str, str], bytes]]


# 新库里没有 WikiRevision 这个类，直接写实例文档会被 TerminusDB 以
# SchemaCheckFailure 拒绝（ascribed_type_does_not_exist），随后被报成
# store_result_unknown。先把类声明进 schema 图，再写实例。
_WIKI_REVISION_SCHEMA = {
    "@type": "Class",
    "@id": "WikiRevision",
    "@key": {"@type": "Lexical", "@fields": ["wiki_revision_id"]},
    "wiki_revision_id": "xsd:string",
    "document_id": {"@type": "Optional", "@class": "xsd:string"},
    "category": {"@type": "Optional", "@class": "xsd:string"},
    "title": {"@type": "Optional", "@class": "xsd:string"},
    "body_markdown": {"@type": "Optional", "@class": "xsd:string"},
    "created_by": {"@type": "Optional", "@class": "xsd:string"},
    "created_at": {"@type": "Optional", "@class": "xsd:string"},
    "lifecycle_state": {"@type": "Optional", "@class": "xsd:string"},
    "wiki_domain_id": {"@type": "Optional", "@class": "xsd:string"},
    "proposal_id": {"@type": "Optional", "@class": "xsd:string"},
    "base_formal_revision_id": {"@type": "Optional", "@class": "xsd:string"},
}



class ExactResourceVersionStore(Protocol):
    """Boundary for reading one immutable ResourceVersion.

    Implementations must return ``missing`` or ``unavailable`` instead of
    guessing a route, falling back to a branch head or returning a snapshot
    whose identity cannot be confirmed.
    """

    def read_resource_version(
        self, location: ResourceVersionLocation, resource_version_id: str
    ) -> ResourceVersionRead: ...


class TerminusDBResourceStore:
    """Fail-closed TerminusDB 12.0.8 adapter for exact ResourceVersion reads.

    The read reuses the exact-commit document route: the version is only
    confirmed when the response echoes the requested ``commit:<hash>`` and the
    snapshot contains exactly one document that represents the requested
    version id. Owner facts are resolved from the Resource document inside the
    same snapshot; when it is absent the owner stays unknown instead of being
    inferred.
    """

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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.remote = remote
        self.timeout = timeout
        self._opener = opener or _urllib_opener
        self._authorization = _resolve_authorization(token, username, password)

    def read_resource_version(
        self, location: ResourceVersionLocation, resource_version_id: str
    ) -> ResourceVersionRead:
        url = self._document_commit_url(location)
        headers = {
            "Accept": "application/json",
            "TerminusDB-Data-Version": f"commit:{location.commit_hash}",
        }
        if self._authorization:
            headers["Authorization"] = self._authorization

        try:
            status, response_headers, body = self._opener(url, headers, self.timeout)
        except (OSError, TimeoutError, urllib.error.URLError):
            return ResourceVersionRead.unavailable(errors.STORE_UNAVAILABLE)

        if status == 404:
            return ResourceVersionRead.missing(errors.VERSION_MISSING)
        if status < 200 or status >= 300:
            return ResourceVersionRead.unavailable(errors.STORE_UNAVAILABLE)

        normalized = {
            str(key).lower(): str(value) for key, value in response_headers.items()
        }
        content_type = normalized.get("content-type", "")
        if "json" not in content_type.lower():
            return ResourceVersionRead.unavailable(errors.UNEXPECTED_CONTENT_TYPE)

        data_version = normalized.get("terminusdb-data-version")
        if data_version is None:
            return ResourceVersionRead.unavailable(errors.DATA_VERSION_MISSING)
        if data_version != f"commit:{location.commit_hash}":
            return ResourceVersionRead.unavailable(errors.DATA_VERSION_MISMATCH)

        try:
            payload: Any = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ResourceVersionRead.unavailable(errors.UNEXPECTED_PAYLOAD)
        if not isinstance(payload, list) or not all(
            isinstance(document, dict) for document in payload
        ):
            return ResourceVersionRead.unavailable(errors.UNEXPECTED_PAYLOAD)

        matches = [
            document
            for document in payload
            if _represents_version(document, resource_version_id)
        ]
        if not matches:
            return ResourceVersionRead.missing(errors.VERSION_MISSING)
        if len(matches) > 1:
            return ResourceVersionRead.unavailable(errors.VERSION_ID_AMBIGUOUS)

        document = matches[0]
        return ResourceVersionRead.confirmed(
            ResourceVersionSnapshot(
                resource_version_id=resource_version_id,
                resource_id=_text(document.get("resource_id")),
                owner_id=_owner_id(document, payload),
                snapshot_digest=sha256_json(document),
                content_digest=_text(document.get("content_checksum_value")),
                content_checksum_algorithm=_text(
                    document.get("content_checksum_algorithm")
                ),
                source_locator=_text(document.get("source_locator")),
                source_external_id=_text(document.get("source_external_id")),
                external_version_id=_text(document.get("external_version_id")),
                current_access_locator=_text(document.get("current_access_locator")),
                availability_status=_text(document.get("availability_status")),
                availability_checked_at=_text(
                    document.get("availability_checked_at")
                ),
                generated_at=_text(document.get("generated_at")),
                generated_by=_text(document.get("generated_by")),
                generated_by_task_id=_text(document.get("generated_by_task_id")),
                license=_text(document.get("license")),
                attribution=_text(document.get("attribution")),
                handling_mode=_text(document.get("handling_mode")),
            )
        )

    def read_exact_snapshot(
        self, store_id: str, database: str, branch_id: str, commit_hash: str
    ) -> WikiSnapshotRead:
        """Read an instance snapshot at the exact commit without head fallback."""
        location = ResourceVersionLocation(store_id, database, branch_id, commit_hash)
        url = self._document_commit_url(location)
        headers = {"Accept": "application/json", "TerminusDB-Data-Version": f"commit:{commit_hash}"}
        if self._authorization:
            headers["Authorization"] = self._authorization
        try:
            status, response_headers, body = self._opener(url, headers, self.timeout)
        except (OSError, TimeoutError, urllib.error.URLError):
            return WikiSnapshotRead.unavailable(errors.STORE_UNAVAILABLE)
        if status == 404:
            return WikiSnapshotRead.missing(errors.COMMIT_MISSING)
        if status < 200 or status >= 300:
            return WikiSnapshotRead.unavailable(errors.STORE_UNAVAILABLE)
        normalized = {str(key).lower(): str(value) for key, value in response_headers.items()}
        if "json" not in normalized.get("content-type", "").lower():
            return WikiSnapshotRead.unavailable(errors.UNEXPECTED_CONTENT_TYPE)
        if normalized.get("terminusdb-data-version") != f"commit:{commit_hash}":
            reason = errors.DATA_VERSION_MISSING if "terminusdb-data-version" not in normalized else errors.DATA_VERSION_MISMATCH
            return WikiSnapshotRead.unavailable(reason)
        try:
            payload: Any = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return WikiSnapshotRead.unavailable(errors.UNEXPECTED_PAYLOAD)
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            return WikiSnapshotRead.unavailable(errors.UNEXPECTED_PAYLOAD)
        return WikiSnapshotRead.confirmed(
            store_id=store_id, database=database, branch_id=branch_id,
            commit_hash=commit_hash, documents=payload,
            content_digest=sha256_json(payload),
        )

    def _document_commit_url(self, location: ResourceVersionLocation) -> str:
        segments = {
            "store": quote(location.store_id, safe=""),
            "database": quote(location.database, safe=""),
            "remote": quote(self.remote, safe=""),
            "commit": quote(location.commit_hash, safe=""),
        }
        return (
            f"{self.base_url}/api/document/{segments['store']}/"
            f"{segments['database']}/{segments['remote']}/commit/{segments['commit']}"
            "?as_list=true&graph_type=instance"
        )


def _represents_version(document: Mapping[str, Any], resource_version_id: str) -> bool:
    if _text(document.get("resource_version_id")) == resource_version_id:
        return True
    return _matches_document_id(_text(document.get("@id")), resource_version_id)


def _owner_id(
    document: Mapping[str, Any], payload: list[dict[str, Any]]
) -> str | None:
    direct = _text(document.get("owner_id"))
    if direct:
        return direct

    resource_id = _text(document.get("resource_id"))
    if not resource_id:
        return None
    candidates = [
        other
        for other in payload
        if other is not document
        and (
            _matches_document_id(_text(other.get("@id")), resource_id)
            or _text(other.get("resource_id")) == resource_id
        )
    ]
    owners = {_text(candidate.get("owner_id")) for candidate in candidates}
    owners.discard(None)
    if len(owners) != 1:
        return None
    return owners.pop()


def _matches_document_id(document_id: str | None, wanted: str) -> bool:
    if not document_id:
        return False
    if document_id == wanted:
        return True
    return document_id.rsplit("/", 1)[-1] == wanted


def _text(value: Any) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("@id")
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _resolve_authorization(
    token: str | None, username: str | None, password: str | None
) -> str | None:
    """Choose one credential form for the request.

    Bearer tokens carry JWT deployments; HTTP Basic carries the local
    ``admin:<store-key>`` credentials the pinned container initializes. The two
    forms are not combined so a misconfiguration fails loudly instead of
    silently sending an unverifiable request.
    """

    if token and (username or password):
        raise ValueError(
            "configure either a TerminusDB token or basic credentials, not both"
        )
    if username or password:
        if not username or not password:
            raise ValueError(
                "TerminusDB basic credentials need both username and password"
            )
        credentials = f"{username}:{password}".encode("utf-8")
        return "Basic " + base64.b64encode(credentials).decode("ascii")
    if token:
        return f"Bearer {token}"
    return None


def _urllib_opener(
    url: str, headers: dict[str, str], timeout: float
) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {}), error.read()


__all__ = [
    "ExactResourceVersionStore",
    "Opener",
    "TerminusDBResourceStore",
    "TerminusDBWikiCandidateStore",
]


class TerminusDBWikiCandidateStore(TerminusDBResourceStore):
    """Write isolated Wiki candidates and confirm their exact immutable commit."""

    def __init__(self, *, store_id: str, database: str, **kwargs):
        self._request_opener = kwargs.pop("request_opener", None)
        super().__init__(**kwargs)
        self.store_id = store_id
        self.database = database
        if self._request_opener is None:
            # ``_request`` needs to send arbitrary methods and a request body, so it
            # must not reuse the 3-argument GET-only ``self._opener`` (which would
            # raise TypeError for every candidate-submission call). Default to a
            # request-shaped opener; tests may still inject one of the same shape.
            self._request_opener = self._urllib_request_opener

    def _urllib_request_opener(self, method, url, headers, body, timeout):
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers or {}), error.read()

    def ensure_default_formal_snapshot(self, domain_id: str):
        """Create or find the immutable empty formal snapshot for one domain."""
        from .candidate_submission import CandidateSnapshotResult

        if not all((domain_id, self.store_id, self.database)):
            return CandidateSnapshotResult("failed", reason_code="formal_store_not_configured")
        domain_key = hashlib.sha256(domain_id.encode("utf-8")).hexdigest()
        revision_id = "wiki-default-" + domain_key
        marker = "sciweave-wiki-default-formal:" + domain_key
        expected = [{
            "@id": "WikiRevision/" + revision_id,
            "@type": "WikiRevision",
            "wiki_revision_id": revision_id,
            "title": "",
            "body_markdown": "",
            "lifecycle_state": "formal",
        }]
        try:
            head = self._candidate_head("main")
            if head and head.get("message") == marker:
                return self._default_formal_readback(revision_id, head.get("identifier"), expected)
            if head is None:
                return CandidateSnapshotResult("unknown", reason_code="store_result_unknown")
            snapshot = self.read_exact_snapshot(self.store_id, self.database, "main", head.get("identifier"))
            if snapshot.status != "confirmed":
                return CandidateSnapshotResult("unknown", reason_code="store_result_unknown")
            if snapshot.documents:
                return CandidateSnapshotResult("failed", reason_code="default_formal_branch_not_empty")
            # 先把 WikiRevision 类声明进 schema 图；新库没有它会拒绝实例写入。
            self._request(
                "POST",
                self._candidate_document_url("main")
                + "?author=sciweave&message=" + quote(marker + ":schema", safe="")
                + "&graph_type=schema",
                json.dumps([_WIKI_REVISION_SCHEMA], ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            )
            status, _, _ = self._request(
                "POST", self._candidate_document_url("main") + "?author=sciweave&message=" + quote(marker, safe=""),
                json.dumps(expected, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            )
            if not 200 <= status < 300:
                head = self._candidate_head("main")
                if not head or head.get("message") != marker:
                    return CandidateSnapshotResult("unknown", reason_code="store_result_unknown")
            head = self._candidate_head("main")
            if not head or head.get("message") != marker:
                return CandidateSnapshotResult("unknown", reason_code="store_result_unknown")
            return self._default_formal_readback(revision_id, head.get("identifier"), expected)
        except Exception:
            return CandidateSnapshotResult("unknown", reason_code="store_result_unknown")

    def _default_formal_readback(self, revision_id, commit, expected):
        from .candidate_submission import CandidateSnapshotResult
        if not isinstance(commit, str) or not commit:
            return CandidateSnapshotResult("unknown", reason_code="store_result_unknown")
        snapshot = self.read_exact_snapshot(self.store_id, self.database, "main", commit)
        if (snapshot.status != "confirmed" or snapshot.commit_hash != commit
                or list(snapshot.documents) != expected):
            return CandidateSnapshotResult("unknown", reason_code="store_result_unknown")
        return CandidateSnapshotResult("confirmed", self.store_id, "main", commit)

    def create_candidate_snapshot(self, domain_id: str, base_commit_ref: str,
                                  canonical_snapshot: str, idempotency_key: str):
        from .candidate_submission import CandidateSnapshotResult
        if not all((self.store_id, self.database, base_commit_ref, idempotency_key)):
            return CandidateSnapshotResult("failed", reason_code="candidate_store_not_configured")
        try:
            documents = json.loads(canonical_snapshot)
            if not isinstance(documents, list) or not all(isinstance(doc, dict) for doc in documents):
                return CandidateSnapshotResult("failed", reason_code="invalid_candidate_snapshot")
            op = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
            branch = "wiki-candidate-" + op
            marker = f"sciweave-wiki-candidate:{op}:{domain_id}:{base_commit_ref}:{sha256_json(documents)}"
            branches = self._candidate_branches()
            if branches is None:
                return CandidateSnapshotResult("unknown", reason_code="store_result_unknown")
            matching_branch = branch in branches
            if not matching_branch:
                status, _, _ = self._request("POST", self._candidate_branch_url(branch), json.dumps({
                    "origin": f"{quote(self.store_id, safe='')}/{quote(self.database, safe='')}/{quote(self.remote, safe='')}/branch/main"
                }, separators=(",", ":")).encode())
                if not 200 <= status < 300:
                    return CandidateSnapshotResult("unknown" if status >= 500 or status == 409 else "failed",
                                                   reason_code="store_result_unknown" if status >= 500 or status == 409 else "store_rejected")
                status, _, _ = self._request("POST", self._candidate_reset_url(branch), json.dumps({
                    "commit_descriptor": f"{quote(self.store_id, safe='')}/{quote(self.database, safe='')}/{quote(self.remote, safe='')}/commit/{quote(base_commit_ref, safe='')}"
                }, separators=(",", ":")).encode())
                if not 200 <= status < 300:
                    return CandidateSnapshotResult("unknown" if status >= 500 else "failed",
                                                   reason_code="store_result_unknown" if status >= 500 else "store_rejected")
            head = self._candidate_head(branch)
            if not head:
                return CandidateSnapshotResult("unknown", reason_code="store_result_unknown")
            if head.get("message") == marker and head.get("author") == "sciweave":
                return self._candidate_reconcile(branch, marker, documents)
            if head.get("identifier") != base_commit_ref:
                return CandidateSnapshotResult("unknown", reason_code="candidate_branch_conflict")
            status, _, _ = self._request("POST", self._candidate_document_url(branch) + "?author=sciweave&message=" + quote(marker, safe=""), canonical_snapshot.encode())
            if not 200 <= status < 300 and status < 500:
                return CandidateSnapshotResult("failed", reason_code="store_rejected")
            return self._candidate_reconcile(branch, marker, documents)
        except (OSError, TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            return CandidateSnapshotResult("unknown", reason_code="store_result_unknown")

    def _candidate_reconcile(self, branch, marker, expected):
        from .candidate_submission import CandidateSnapshotResult
        head = self._candidate_head(branch)
        if not head or head.get("message") != marker or head.get("author") != "sciweave":
            return CandidateSnapshotResult("unknown", reason_code="store_result_unknown")
        commit = head.get("identifier")
        snapshot = self.read_exact_snapshot(self.store_id, self.database, branch, commit)
        if snapshot.status != "confirmed" or not _candidate_documents_match(snapshot.documents, expected):
            return CandidateSnapshotResult("unknown", reason_code="store_result_unknown")
        return CandidateSnapshotResult("confirmed", self.store_id, branch, commit)

    def create_formal_snapshot(self, candidate_ref, operation_id):
        """Write the locked candidate to the formal branch and confirm its exact Commit.

        Any ambiguous write outcome is resolved only by finding the operation marker
        in the formal branch log and validating the complete exact-Commit snapshot.
        """
        from .candidate_submission import CandidateSnapshotResult
        try:
            source = self.read_exact_snapshot(candidate_ref["store_id"], candidate_ref["database"],
                                              candidate_ref["branch_id"], candidate_ref["commit_hash"])
            if source.status != "confirmed":
                return {"status": "unknown", "reason_code": "candidate_unavailable"}
            documents = [dict(doc) for doc in source.documents]
            for document in documents:
                if document.get("@type") == "WikiRevision":
                    document["lifecycle_state"] = "formal"
            marker = "sciweave-wiki-formalization:" + operation_id
            branch = "main"
            head = self._candidate_head(branch)
            if not head or head.get("message") != marker:
                existing = self.read_exact_snapshot(self.store_id, self.database, branch, head.get("identifier")) if head else None
                if existing is None or existing.status != "confirmed":
                    return {"status": "unknown", "reason_code": "formal_head_unverified"}
                existing_by_id = {doc.get("@id"): doc for doc in existing.documents if doc.get("@id")}
                additions = []
                for document in documents:
                    prior = existing_by_id.get(document.get("@id"))
                    if prior is None:
                        additions.append(document)
                    elif prior != document:
                        return {"status": "failed", "reason_code": "formal_document_conflict"}
                if additions:
                    status, _, _ = self._request("POST", self._candidate_document_url(branch) +
                        "?author=sciweave&message=" + quote(marker, safe=""),
                        json.dumps(additions, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                    if not 200 <= status < 300:
                        head = self._candidate_head(branch)
                        if not head or head.get("message") != marker:
                            return {"status": "unknown" if status >= 500 else "failed",
                                    "reason_code": "formal_write_unknown" if status >= 500 else "formal_write_rejected"}
                else:
                    return {"status": "failed", "reason_code": "formal_snapshot_has_no_new_documents"}
            head = self._candidate_head(branch)
            if not head or head.get("message") != marker:
                return {"status": "unknown", "reason_code": "formal_commit_unconfirmed"}
            commit = head.get("identifier")
            verified = self.read_exact_snapshot(self.store_id, self.database, branch, commit)
            if verified.status != "confirmed" or list(verified.documents) != documents:
                return {"status": "unknown", "reason_code": "formal_snapshot_unverified"}
            return {"status": "confirmed", "store_id": self.store_id, "branch_id": branch, "commit_hash": commit}
        except Exception:
            return {"status": "unknown", "reason_code": "formal_write_unknown"}

    def verify_formalization_commit(self, store_id, database, branch_id, commit_hash, operation_id):
        """Confirm the exact formal Commit carries this operation's log marker."""
        if (store_id, database, branch_id) != (self.store_id, self.database, "main"):
            return False
        url = (f"{self.base_url}/api/log/{quote(store_id, safe='')}/"
               f"{quote(database, safe='')}/{quote(self.remote, safe='')}/branch/"
               f"{quote(branch_id, safe='')}?count=1000")
        status, _, body = self._request("GET", url)
        if not 200 <= status < 300:
            return False
        try:
            entries = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        marker = "sciweave-wiki-formalization:" + operation_id
        if not isinstance(entries, list) or not any(
            isinstance(entry, dict) and entry.get("identifier") == commit_hash
            and entry.get("message") == marker for entry in entries
        ):
            return False
        snapshot = self.read_exact_snapshot(store_id, database, branch_id, commit_hash)
        return snapshot.status == "confirmed" and snapshot.commit_hash == commit_hash

    def read_branch_head(self, store, database, branch):
        if (store, database) != (self.store_id, self.database):
            return None
        head = self._candidate_head(branch)
        return head.get("identifier") if isinstance(head, dict) else None

    def _request(self, method, url, body=None):
        headers = {"Accept": "application/json"}
        if self._authorization:
            headers["Authorization"] = self._authorization
        if body is not None:
            headers["Content-Type"] = "application/json"
        # ``_request_opener`` is a 5-argument (method, url, headers, body, timeout)
        # opener, distinct from the 3-argument GET-only ``self._opener``. Routing
        # through it lets tests inject a stub while the default builds a real
        # Request, so arbitrary methods and bodies work.
        return self._request_opener(method, url, headers, body, self.timeout)

    def _candidate_branches(self):
        status, _, body = self._request("GET", self._candidate_database_url() + "?branches=true")
        try:
            payload = json.loads(body.decode("utf-8"))
            branches = payload.get("branches") if isinstance(payload, dict) else None
            return set(branches) if status in range(200, 300) and isinstance(branches, list) else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _candidate_head(self, branch):
        url = self._candidate_log_url(branch) + "?count=1"
        status, _, body = self._request("GET", url)
        try:
            entries = json.loads(body.decode("utf-8"))
            return entries[0] if status in range(200, 300) and isinstance(entries, list) and entries and isinstance(entries[0], dict) else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _candidate_database_url(self):
        return f"{self.base_url}/api/db/{quote(self.store_id, safe='')}/{quote(self.database, safe='')}"

    def _candidate_branch_url(self, branch):
        return f"{self.base_url}/api/branch/{quote(self.store_id, safe='')}/{quote(self.database, safe='')}/{quote(self.remote, safe='')}/branch/{quote(branch, safe='')}"

    def _candidate_reset_url(self, branch):
        return f"{self.base_url}/api/reset/{quote(self.store_id, safe='')}/{quote(self.database, safe='')}/{quote(self.remote, safe='')}/branch/{quote(branch, safe='')}"

    def _candidate_document_url(self, branch):
        return f"{self.base_url}/api/document/{quote(self.store_id, safe='')}/{quote(self.database, safe='')}/{quote(self.remote, safe='')}/branch/{quote(branch, safe='')}"

    def _candidate_log_url(self, branch):
        return f"{self.base_url}/api/log/{quote(self.store_id, safe='')}/{quote(self.database, safe='')}/{quote(self.remote, safe='')}/branch/{quote(branch, safe='')}"

    # --- candidate branch reaping (ai4-4g9s) --------------------------------
    # Every candidate submission leaves a ``wiki-candidate-*`` branch behind, so a
    # busy domain accumulates branches without bound. Reaping is deliberately
    # conservative and explicit: a caller passes the set of branch ids that are
    # still active (derived from non-terminal submissions) and we only delete the
    # rest. ``main`` (and any name not matching the candidate prefix) is never
    # touched, and a domain with an unresolved candidate head is skipped.

    _CANDIDATE_BRANCH_PREFIX = "wiki-candidate-"

    def list_candidate_branches(self) -> list[str] | None:
        """Return the ``wiki-candidate-*`` branches, or None if the store is unreadable."""
        branches = self._candidate_branches()
        if branches is None:
            return None
        return sorted(name for name in branches if isinstance(name, str) and name.startswith(self._CANDIDATE_BRANCH_PREFIX))

    def delete_candidate_branch(self, branch: str) -> bool:
        """Delete one candidate branch. Refuses anything off the candidate namespace."""
        if not isinstance(branch, str) or not branch.startswith(self._CANDIDATE_BRANCH_PREFIX):
            raise ValueError("refusing to delete a non-candidate branch")
        url = (
            f"{self.base_url}/api/branch/{quote(self.store_id, safe='')}/{quote(self.database, safe='')}"
            f"/{quote(self.remote, safe='')}/branch/{quote(branch, safe='')}"
        )
        status, _, _ = self._request("DELETE", url)
        return 200 <= status < 300

    def reap_candidate_branches(self, keep: set[str]) -> dict[str, list[str]]:
        """Delete candidate branches not in ``keep``.

        ``keep`` holds the branch ids that are still active (a branch with a live
        candidate must never be dropped, or a later formalize would fail with a
        missing branch). Returns the deleted and failed branch names.
        """
        candidates = self.list_candidate_branches()
        if candidates is None:
            return {"deleted": [], "failed": [], "skipped": ["store_unreadable"]}
        deleted: list[str] = []
        failed: list[str] = []
        for branch in candidates:
            if branch in keep:
                continue
            if self.delete_candidate_branch(branch):
                deleted.append(branch)
            else:
                failed.append(branch)
        return {"deleted": deleted, "failed": failed, "skipped": []}



def _candidate_documents_match(actual, expected):
    for wanted in expected:
        key = "wiki_revision_id" if wanted.get("@type") == "WikiRevision" else "reference_id"
        wanted_norm = {k: v for k, v in wanted.items() if k != "@id"}
        if not any(
            isinstance(doc, dict)
            and doc.get(key) == wanted.get(key)
            and {k: v for k, v in doc.items() if k != "@id"} == wanted_norm
            for doc in actual
        ):
            return False
    return True
