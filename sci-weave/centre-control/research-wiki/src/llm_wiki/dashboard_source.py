from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Iterable, Mapping

from .formal_domain import WikiFormalQueryResult, WikiSnapshotRead


def build_wiki_fragment(
    formal_result: WikiFormalQueryResult,
    candidates: Iterable[Any] = (),
    *,
    observed_at: str | None = None,
) -> dict[str, object]:
    observed_at = observed_at or _utc_now()
    documents: list[dict[str, object]] = []
    if formal_result.status == "available":
        documents.append({
            "id": formal_result.formal_wiki_revision_id or "unknown-revision",
            "title": formal_result.title or "未命名正式文档",
            "domainId": formal_result.wiki_domain_id,
            "formalRevisionId": formal_result.formal_wiki_revision_id,
            "summary": formal_result.description or "当前已激活的正式 Wiki 版本。",
            "updatedAt": observed_at,
            "references": [_reference_projection(reference) for reference in formal_result.references],
        })

    candidate_rows: list[dict[str, object]] = []
    for candidate in candidates:
        candidate_status = _candidate_state(
            _value(candidate, "submission_status") or _value(candidate, "status"),
            _value(candidate, "proposal_status"),
            _value(candidate, "merge_request_status"),
            _value(candidate, "owner_decision"),
        )
        snapshot_status = _value(candidate, "candidate_snapshot_status")
        candidate_row = {
            "id": _value(candidate, "submission_id") or _value(candidate, "proposal_id") or "unknown-candidate",
            "title": _value(candidate, "title") or f"候选 Proposal {_value(candidate, 'proposal_id') or 'unknown'}",
            "proposalId": _value(candidate, "proposal_id") or "unknown-proposal",
            "state": candidate_status,
            "updatedAt": _value(candidate, "submitted_at") or observed_at,
            "references": _value(candidate, "references") if isinstance(_value(candidate, "references"), list) else [],
        }
        if snapshot_status in {"confirmed", "unavailable", "pending"}:
            candidate_row["candidateSnapshotStatus"] = snapshot_status
        candidate_rows.append(candidate_row)

    candidate_snapshot_unavailable = any(row.get("candidateSnapshotStatus") == "unavailable" for row in candidate_rows)
    source_status = "fresh" if formal_result.status == "available" and not candidate_snapshot_unavailable else ("partial" if candidate_rows else "unavailable")
    return {
        "observedAt": observed_at,
        "sourceStatus": source_status,
        "wikiDocuments": documents,
        "wikiCandidates": candidate_rows,
        "events": [{
            "id": f"wiki-formal:{formal_result.formal_wiki_revision_id or 'unavailable'}",
            "type": "formal_release" if formal_result.status == "available" else "candidate_change",
            "title": "LLM-Wiki 正式版本已发布" if formal_result.status == "available" else "LLM-Wiki 正式查询暂不可用",
            "occurredAt": observed_at,
            "diagnostic": f"reason: {formal_result.reason_code}",
        }],
    }


def project_candidate_references(
    documents: Iterable[Mapping[str, object]],
    qualification_reader: Callable[[str, str | None], Any],
) -> list[dict[str, object]]:
    references: list[dict[str, object]] = []
    for document in documents:
        if str(document.get("@type", "")).replace("_", "").lower() != "resourcereference":
            continue
        resource_version_id = _text(document.get("target_resource_version_id"))
        if not resource_version_id:
            continue
        scope = _text(document.get("requested_scope")) or _text(document.get("reference_role"))
        try:
            qualification = qualification_reader(resource_version_id, scope)
            status = _qualification_status(getattr(qualification, "status", None))
            limitations = list(getattr(qualification, "limitations", ()) or ())
            requested_scope = ", ".join(str(item) for item in (getattr(qualification, "use_scope", ()) or ()) if isinstance(item, str) and item.strip()) or scope or "unspecified"
        except Exception:
            status = "unknown"
            limitations = []
            requested_scope = scope or "unspecified"
        references.append({
            "id": _text(document.get("reference_id")) or _text(document.get("@id")) or "unknown-reference",
            "resourceVersionId": resource_version_id,
            "qualification": status,
            "requestedScope": requested_scope,
            "limitations": limitations,
        })
    return references


def _reference_projection(reference: Any) -> dict[str, object]:
    qualification = getattr(reference, "qualification", None)
    use_scope = getattr(qualification, "use_scope", ()) if qualification is not None else ()
    requested_scope = ", ".join(str(item) for item in use_scope if isinstance(item, str) and item.strip())
    return {
        "id": getattr(reference, "reference_id", "unknown-reference"),
        "resourceVersionId": getattr(reference, "target_resource_version_id", None) or "unknown-resource-version",
        "qualification": _qualification_status(getattr(qualification, "status", None)),
        "requestedScope": requested_scope or getattr(reference, "reference_role", "unspecified"),
        "limitations": list(getattr(qualification, "limitations", ()) or ()),
    }


def _qualification_status(value: object) -> str:
    return value if value in {"approved", "pending", "rejected", "revoked", "unknown"} else "unknown"


def _candidate_state(submission_status: object, proposal_status: object = None, merge_request_status: object = None, owner_decision: object = None) -> str:
    if proposal_status == "merged":
        return "formalized"
    if owner_decision == "rejected" or merge_request_status == "rejected":
        return "rejected"
    if owner_decision == "approved" or merge_request_status == "approved":
        return "approved_pending_formalization"
    if merge_request_status in {"ready_for_owner", "reapproval_required"}:
        return "review_pending"
    if proposal_status == "candidate" or submission_status == "candidate_created":
        return "candidate"
    if submission_status == "pending":
        return "review_pending"
    if submission_status == "revoked":
        return "revoked"
    return "candidate"

def _value(value: object, name: str) -> str | object | None:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class _WikiDashboardHandler(BaseHTTPRequestHandler):
    server_version = "SciWeaveLLMWiki/1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(HTTPStatus.NO_CONTENT, None)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(HTTPStatus.OK, {"status": "ready", "api_version": "wiki-dashboard-v1"})
            return
        if self.path != "/api/dashboard/source/wiki":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        token = self.server.dashboard_token  # type: ignore[attr-defined]
        if token and self.headers.get("Authorization") != f"Bearer {token}":
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        try:
            self._send(HTTPStatus.OK, self.server.read_fragment())  # type: ignore[attr-defined]
        except Exception:
            self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "wiki_query_unavailable"})

    def do_POST(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

    def _send(self, status: HTTPStatus, payload: object) -> None:
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class WikiDashboardServer(ThreadingHTTPServer):
    allow_reuse_address = True


def create_wiki_dashboard_server(read_fragment: Callable[[], Mapping[str, object]], *, host: str, port: int, token: str | None = None) -> WikiDashboardServer:
    server = WikiDashboardServer((host, port), _WikiDashboardHandler)
    server.read_fragment = read_fragment  # type: ignore[attr-defined]
    server.dashboard_token = token  # type: ignore[attr-defined]
    return server


def run_wiki_dashboard_from_environment(read_fragment: Callable[[], Mapping[str, object]]) -> int:
    host = os.environ.get("SCIWEAVE_WIKI_DASHBOARD_HOST", "").strip()
    port_text = os.environ.get("SCIWEAVE_WIKI_DASHBOARD_PORT", "").strip()
    if not host or not port_text:
        raise RuntimeError("SCIWEAVE_WIKI_DASHBOARD_HOST and SCIWEAVE_WIKI_DASHBOARD_PORT are required")
    server = create_wiki_dashboard_server(read_fragment, host=host, port=int(port_text), token=os.environ.get("SCIWEAVE_WIKI_DASHBOARD_TOKEN") or None)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0
