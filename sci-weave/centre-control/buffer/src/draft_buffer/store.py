from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

from . import BufferError


class TerminusDBDraftStore:
    """TerminusDB 12.0.8 adapter for one draft database and two namespaces."""

    def __init__(self, *, base_url: str, database: str, username: str | None = None,
                 password: str | None = None, token: str | None = None, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.database = database
        self.timeout = timeout
        if token and (username or password):
            raise ValueError("configure either a token or basic credentials, not both")
        if username and password:
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            self.authorization = f"Basic {credentials}"
        else:
            self.authorization = f"Bearer {token}" if token else None

    def request(self, method: str, path: str, payload: Any = None) -> tuple[int, dict[str, str], bytes]:
        headers = {"Accept": "application/json"}
        # TerminusDB 12.0.8 rejects "schema"/"instance" as TerminusDB-Data-Version
        # request values and returns the snapshot version (branch:<head>) in the
        # response header instead; reads confirm it in read_all.
        if self.authorization:
            headers["Authorization"] = self.authorization
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode() if payload is not None else None
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, dict(response.headers.items()), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers.items()) if error.headers else {}, error.read()
        except (OSError, TimeoutError, urllib.error.URLError):
            raise BufferError("store_unavailable", "TerminusDB request could not be confirmed") from None

    def initialize_schema(self) -> None:
        optional_string = {"@type": "Optional", "@class": "xsd:string"}
        payload = [
            {"@type":"Class","@id":"Draft","@key":{"@type":"Random"},"draft_id":"xsd:string","namespace":"xsd:string","kind":"xsd:string","title":"xsd:string","submitted_by":"xsd:string","submitted_at":"xsd:string","status":"xsd:string","base_formal_revision_id":dict(optional_string),"source_task_node_id":dict(optional_string),"source_execution_record_id":dict(optional_string),"payload":"sys:JSON","submitted_commit":dict(optional_string),"reviewer_id":dict(optional_string),"review_decided_at":dict(optional_string),"review_reason":dict(optional_string),"supersedes_draft_id":dict(optional_string),"last_idempotency_key":dict(optional_string),"promoted_candidate_id":dict(optional_string),"promoted_candidate_commit":dict(optional_string)},
            {"@type":"Class","@id":"NamespaceConfig","@key":{"@type":"Random"},"namespace":"xsd:string","reviewer_ids":{"@type":"Set","@class":"xsd:string"},"allowed_kinds":{"@type":"Set","@class":"xsd:string"},"promotion_target":dict(optional_string)},
            {"@type":"Class","@id":"Operation","@key":{"@type":"Random"},"operation_id":"xsd:string","idempotency_key":"xsd:string","operation":"xsd:string","request_digest":"xsd:string","result_json":"xsd:string"},
        ]
        status, _, body = self.request("POST", f"/api/document/{quote('admin', safe='')}/{quote(self.database, safe='')}?graph_type=schema&author=sciweave&message=initialize-buffer-schema", payload)
        if status in (200, 201, 409):
            return
        # TerminusDB answers 400 (api:DocumentIdAlreadyExists) rather than 409 when
        # the classes are already in the schema, so a restart against an existing
        # database used to look like a fatal schema error. Only accept that answer
        # once the schema really holds every class we need.
        if status == 400 and self._schema_is_initialized(payload):
            return
        raise BufferError("schema_initialization_failed", f"TerminusDB schema initialization returned HTTP {status}")

    def _schema_is_initialized(self, payload: list[dict[str, Any]]) -> bool:
        status, _, body = self.request("GET", f"/api/document/{quote('admin', safe='')}/{quote(self.database, safe='')}?graph_type=schema&as_list=true")
        if not 200 <= status < 300:
            return False
        try:
            present = {
                item.get("@id")
                for item in json.loads(body.decode("utf-8"))
                if isinstance(item, dict)
            }
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return {item["@id"] for item in payload} <= present

    def read_all(self) -> list[dict[str, Any]]:
        status, headers, body = self.request("GET", f"/api/document/admin/{quote(self.database, safe='')}/local/branch/main?as_list=true&graph_type=instance")
        if status == 404:
            return []
        if not 200 <= status < 300:
            raise BufferError("store_read_failed", f"TerminusDB read returned HTTP {status}")
        if not any(key.lower() == "terminusdb-data-version" for key in headers):
            raise BufferError("store_result_unconfirmed", "TerminusDB did not confirm the snapshot version")
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise BufferError("store_result_unconfirmed", "TerminusDB returned invalid JSON") from None
        if not isinstance(decoded, list) or not all(isinstance(item, dict) for item in decoded):
            raise BufferError("store_result_unconfirmed", "TerminusDB returned an unexpected document shape")
        return decoded

    def write(self, documents: list[dict[str, Any]], operation: str, idempotency_key: str) -> str:
        """Persist a document set and confirm the exact branch-head commit.

        TerminusDB 12.0.8 rejects a POST for an @id that already exists, so
        existing documents are updated through PUT with their full
        ``terminusdb:///data/...`` id while new documents are inserted via POST.
        The exact commit is confirmed from the branch log afterwards; when the
        write cannot be confirmed the operation fails closed.
        """
        marker = f"sciweave-buffer:{operation}:{idempotency_key}"
        current = self.read_all()
        existing: dict[str, dict[str, Any]] = {}
        for doc in current:
            if isinstance(doc, dict) and isinstance(doc.get("@id"), str):
                existing[_full_id(doc["@id"])] = doc
        posts: list[dict[str, Any]] = []
        puts: list[dict[str, Any]] = []
        for doc in documents:
            if not isinstance(doc, dict):
                continue
            raw_id = doc.get("@id")
            if isinstance(raw_id, str):
                full = _full_id(raw_id)
                if full in existing:
                    puts.append({**doc, "@id": full})
                    continue
            posts.append(doc)
        doc_url = f"/api/document/admin/{quote(self.database, safe='')}?author=sciweave&message={quote(marker, safe='')}"
        if posts:
            status, _, _ = self.request("POST", doc_url, posts)
            if status not in (200, 201):
                raise BufferError("store_write_unknown" if status >= 500 else "store_write_failed", f"TerminusDB write returned HTTP {status}")
        if puts:
            status, _, _ = self.request("PUT", doc_url, puts)
            if status not in (200, 201):
                raise BufferError("store_write_unknown" if status >= 500 else "store_write_failed", f"TerminusDB write returned HTTP {status}")
        commit = self._branch_head_commit()
        if not commit:
            raise BufferError("store_write_unknown", "TerminusDB write succeeded but its exact commit could not be confirmed")
        return commit

    def _branch_head_commit(self) -> str | None:
        status, _, body = self.request("GET", f"/api/log/admin/{quote(self.database, safe='')}/local/branch/main?count=1")
        if status != 200:
            return None
        try:
            entries = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if isinstance(entries, list) and entries and isinstance(entries[0], dict):
            commit = entries[0].get("identifier")
            if isinstance(commit, str) and commit:
                return commit
        return None


def _full_id(short_id: str) -> str:
    """Expand a short TerminusDB document id to its full data URI for PUT."""
    if short_id.startswith("terminusdb:///data/"):
        return short_id
    return "terminusdb:///data/" + short_id.lstrip("/")
