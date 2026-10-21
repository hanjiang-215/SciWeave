from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from urllib.parse import quote

from . import errors
from .domain import SNAPSHOT_CONFIRMED, SnapshotRead

Opener = Callable[[str, dict[str, str], float], tuple[int, Mapping[str, str], bytes]]


class ExactSnapshotStore(Protocol):
    """Boundary for reading one exact formal snapshot.

    Implementations must return ``missing`` or ``unavailable`` rather than
    falling back to a branch head or an empty snapshot.
    """

    def read_exact_snapshot(
        self, store_id: str, database: str, branch_id: str, commit_hash: str
    ) -> SnapshotRead: ...


class TerminusDBStore:
    """Fail-closed TerminusDB 12.0.8 adapter for exact commit reads."""

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
            status, response_headers, body = self._opener(
                url, headers, self.timeout
            )
        except (OSError, TimeoutError, urllib.error.URLError):
            return SnapshotRead.unavailable(errors.STORE_UNAVAILABLE)

        if status == 404:
            return SnapshotRead.missing()
        if status < 200 or status >= 300:
            return SnapshotRead.unavailable(errors.STORE_UNAVAILABLE)

        normalized = {
            str(key).lower(): str(value) for key, value in response_headers.items()
        }
        content_type = normalized.get("content-type", "")
        if "json" not in content_type.lower():
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
        if not isinstance(payload, list) or not all(
            isinstance(document, dict) for document in payload
        ):
            return SnapshotRead.unavailable(errors.UNEXPECTED_PAYLOAD)

        return SnapshotRead.confirmed(
            store_id=store_id,
            database=database,
            branch_id=branch_id,
            commit_hash=commit_hash,
            documents=payload,
        )

    def _document_commit_url(
        self, store_id: str, database: str, commit_hash: str
    ) -> str:
        segments = {
            "store": quote(store_id, safe=""),
            "database": quote(database, safe=""),
            "remote": quote(self.remote, safe=""),
            "commit": quote(commit_hash, safe=""),
        }
        return (
            f"{self.base_url}/api/document/{segments['store']}/"
            f"{segments['database']}/{segments['remote']}/commit/{segments['commit']}"
            "?as_list=true&graph_type=instance"
        )


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
