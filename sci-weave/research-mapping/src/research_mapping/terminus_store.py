from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from urllib.parse import quote

from . import errors
from .canonical import canonical_json
from .domain import SNAPSHOT_CONFIRMED, SnapshotRead

Opener = Callable[[str, dict[str, str], float], tuple[int, Mapping[str, str], bytes]]
RequestOpener = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, Mapping[str, str], bytes]]


class CandidateSnapshotStore(Protocol):
    """Candidate write seam; unknown outcomes must never be treated as success."""

    def create_candidate_snapshot(
        self, domain_id: str, base_commit_ref: str, canonical_snapshot: str,
        idempotency_key: str,
    ) -> CandidateSnapshotResult: ...


@dataclass(frozen=True)
class CandidateSnapshotResult:
    """Explicit result of a candidate snapshot write attempt."""

    status: str
    store_id: str | None = None
    branch_id: str | None = None
    commit_hash: str | None = None
    reason_code: str | None = None



def _contains_documents(actual, expected):
    """Confirm every submitted document exists unchanged in the exact commit."""
    by_id = {document.get("@id"): document for document in actual if isinstance(document, dict)}
    return all(
        isinstance(document.get("@id"), str) and by_id.get(document["@id"]) == document
        for document in expected
    )


class ExactSnapshotStore(Protocol):
    """Boundary for reading one exact formal snapshot."""

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
        suffix = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16]
        branch = f"candidate-{suffix}"
        marker = f"sciweave-candidate:{suffix}:{digest}"
        try:
            branches = self._branches()
            if branches is None:
                return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)
            if branch not in branches:
                status, _, _ = self._request(
                    "POST", self._branch_url(branch), json.dumps({}, separators=(",", ":")).encode()
                )
                if not 200 <= status < 300:
                    # A conflict can mean a previous timed-out create. Re-read
                    # state; never infer creation from the response alone.
                    if status not in (409, 422):
                        return CandidateSnapshotResult("failed", reason_code="store_rejected")
                    branches = self._branches()
                    if branches is None or branch not in branches:
                        return CandidateSnapshotResult("unknown", reason_code=errors.STORE_RESULT_UNKNOWN)
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

            headers = {"Content-Type": "application/json"}
            if self._authorization:
                headers["Authorization"] = self._authorization
            url = self._branch_document_url(branch) + "?author=sciweave&message=" + quote(marker, safe="")
            status, response_headers, _ = self._request_opener(
                "POST", url, headers, canonical_snapshot.encode("utf-8"), self.timeout
            )
            if not 200 <= status < 300:
                if status >= 500:
                    return self._reconcile(branch, marker, documents, digest)
                return CandidateSnapshotResult("failed", reason_code="store_rejected")
            return self._reconcile(branch, marker, documents, digest, response_headers)
        except (OSError, TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            return self._reconcile(branch, marker, documents, digest)

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
