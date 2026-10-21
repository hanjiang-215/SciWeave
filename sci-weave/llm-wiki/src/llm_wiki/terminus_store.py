from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from urllib.parse import quote

from . import errors
from .canonical import sha256_json
from .domain import (
    ResourceVersionLocation,
    ResourceVersionRead,
    ResourceVersionSnapshot,
)

Opener = Callable[[str, dict[str, str], float], tuple[int, Mapping[str, str], bytes]]


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
]
