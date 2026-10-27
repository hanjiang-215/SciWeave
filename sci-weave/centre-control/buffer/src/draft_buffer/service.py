from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from . import BufferError
from .canonical import canonical_json, sha256_json

_NAMESPACES = {"mapping", "wiki"}
_ALLOWED_KINDS = {"mapping": {"mapping_change"}, "wiki": {"wiki_document"}}


class DraftBufferService:
    def __init__(self, store, reviewers: dict[str, frozenset[str]]):
        self.store = store
        self.reviewers = reviewers
        self.store.initialize_schema()

    def create_draft(self, namespace: str, kind: str, title: str, payload: Any,
                     submitted_by: str, idempotency_key: str,
                     base_formal_revision_id: str | None = None,
                     source_task_node_id: str | None = None,
                     source_execution_record_id: str | None = None) -> dict[str, Any]:
        self._require(namespace in _NAMESPACES, "invalid_namespace", "namespace must be mapping or wiki")
        self._require(kind in _ALLOWED_KINDS[namespace], "invalid_kind", "kind is not allowed in this namespace")
        self._require(bool(title.strip()) and bool(submitted_by.strip()) and bool(idempotency_key.strip()), "invalid_submission", "title, submitter, and idempotency key are required")
        request = {"namespace": namespace, "kind": kind, "title": title.strip(), "payload": payload,
                   "submitted_by": submitted_by.strip(), "base_formal_revision_id": base_formal_revision_id,
                   "source_task_node_id": source_task_node_id, "source_execution_record_id": source_execution_record_id}
        return self._mutate("create_draft", idempotency_key, request, lambda docs: self._create(request))

    def update_draft(self, draft_id: str, idempotency_key: str, title: str | None = None,
                     payload: Any = None, actor_id: str | None = None) -> dict[str, Any]:
        request = {"draft_id": draft_id, "actor_id": actor_id or "", "title": title, "payload": payload}
        return self._mutate("update_draft", idempotency_key, request, lambda docs: self._update(docs, request))

    def submit_draft(self, draft_id: str, idempotency_key: str, actor_id: str | None = None) -> dict[str, Any]:
        request = {"draft_id": draft_id, "actor_id": actor_id or "", "idempotency_key": idempotency_key}
        return self._mutate("submit_draft", idempotency_key, request, lambda docs: self._submit(docs, request))

    def review_draft(self, draft_id: str, decision: str, reason: str, idempotency_key: str,
                     actor_id: str | None = None) -> dict[str, Any]:
        self._require(decision in {"accept", "reject"}, "invalid_decision", "decision must be accept or reject")
        self._require(bool(reason.strip()), "reason_required", "review reason is required")
        request = {"draft_id": draft_id, "actor_id": actor_id or "", "decision": decision, "reason": reason.strip()}
        return self._mutate("review_draft", idempotency_key, request, lambda docs: self._review(docs, request))

    def mark_promoted(self, draft_id: str, candidate_id: str, candidate_commit: str, idempotency_key: str,
                      actor_id: str | None = None) -> dict[str, Any]:
        request = {"draft_id": draft_id, "actor_id": actor_id or "", "candidate_id": candidate_id, "candidate_commit": candidate_commit}
        return self._mutate("mark_promoted", idempotency_key, request, lambda docs: self._promote(docs, request))

    def read_draft(self, draft_id: str, submitted_commit: str | None = None, actor_id: str = "") -> dict[str, Any]:
        draft = self._find(self.store.read_all(), draft_id)
        self._authorize_namespace(draft["namespace"], actor_id)
        if submitted_commit and draft.get("submitted_commit") != submitted_commit:
            raise BufferError("submitted_commit_mismatch", "requested commit is not the frozen review snapshot")
        return {"draft": draft, **({"snapshot_commit": submitted_commit} if submitted_commit else {})}

    def list_drafts(self, namespace: str | None = None, status: str | None = None,
                    submitted_by: str | None = None, actor_id: str = "") -> list[dict[str, Any]]:
        if namespace is None:
            raise BufferError("namespace_required", "namespace is required")
        self._authorize_namespace(namespace, actor_id)
        return sorted([item for item in self.store.read_all() if item.get("@type") == "Draft"
                       and item.get("namespace") == namespace
                       and (status is None or item.get("status") == status)
                       and (submitted_by is None or item.get("submitted_by") == submitted_by)],
                      key=lambda item: (item.get("submitted_at", ""), item.get("draft_id", "")))

    def _mutate(self, operation: str, key: str, request: dict[str, Any], mutation) -> dict[str, Any]:
        self._require(bool(key.strip()), "idempotency_key_required", "idempotency key is required")
        docs = self.store.read_all()
        digest = sha256_json(request)
        prior = next((item for item in docs if item.get("@type") == "Operation" and item.get("idempotency_key") == key), None)
        if prior:
            if prior.get("request_digest") != digest or prior.get("operation") != operation:
                raise BufferError("idempotency_conflict", "idempotency key was used for a different request")
            return json.loads(prior["result_json"])
        draft, result = mutation(docs)
        if draft is not None:
            docs = [item for item in docs if item.get("draft_id") != draft["draft_id"]]
            docs.append(draft)
        if operation == "submit_draft":
            if draft.get("submitted_commit"):
                # A previous attempt froze the snapshot and then failed before
                # writing the operation row (ai4-6qht). Re-freezing would move
                # the review snapshot, so the existing commit is kept and the
                # retry only writes the missing operation row.
                commit = draft["submitted_commit"]
            else:
                commit = self.store.write(docs, operation, key + ":submitted")
                draft["submitted_commit"] = commit
                docs = [item for item in docs if item.get("draft_id") != draft["draft_id"]] + [draft]
        else:
            commit = None
        result = {**result, "snapshot_commit": commit}
        docs.append({"@type": "Operation", "operation_id": str(uuid.uuid4()), "idempotency_key": key,
                     "operation": operation, "request_digest": digest, "result_json": canonical_json(result)})
        final_commit = self.store.write(docs, operation, key)
        return {**result, "snapshot_commit": draft.get("submitted_commit") if operation == "submit_draft" else final_commit}

    def _create(self, request):
        draft_id = str(uuid.uuid4())
        now = _now()
        return ({"@type": "Draft", "draft_id": draft_id, "namespace": request["namespace"], "kind": request["kind"],
                 "title": request["title"], "submitted_by": request["submitted_by"], "submitted_at": now,
                 "status": "drafting", "base_formal_revision_id": request["base_formal_revision_id"],
                 "source_task_node_id": request["source_task_node_id"], "source_execution_record_id": request["source_execution_record_id"],
                 "payload": request["payload"], "submitted_commit": None, "reviewer_id": None,
                 "review_decided_at": None, "review_reason": None, "supersedes_draft_id": None,
                 "promoted_candidate_id": None, "promoted_candidate_commit": None}, {"draft_id": draft_id, "status": "drafting"})

    def _update(self, docs, request):
        draft = copy.deepcopy(self._find(docs, request["draft_id"]))
        self._require(bool(request["actor_id"]), "identity_required", "authenticated caller identity is required")
        self._require(draft["submitted_by"] == request["actor_id"], "forbidden", "only the submitter may edit this draft")
        self._require(draft["status"] in {"drafting", "rejected"}, "invalid_transition", "draft is not editable in its current state")
        if request["title"] is not None:
            self._require(bool(request["title"].strip()), "invalid_title", "title must not be empty")
            draft["title"] = request["title"].strip()
        if request["payload"] is not None:
            draft["payload"] = request["payload"]
        if draft["status"] == "rejected":
            old_id = draft["draft_id"]
            draft.update({"draft_id": str(uuid.uuid4()), "status": "drafting", "supersedes_draft_id": old_id,
                          "submitted_commit": None, "reviewer_id": None, "review_decided_at": None, "review_reason": None})
        return draft, {"draft_id": draft["draft_id"], "status": draft["status"]}

    def _submit(self, docs, request):
        draft = copy.deepcopy(self._find(docs, request["draft_id"]))
        self._require(bool(request["actor_id"]), "identity_required", "authenticated caller identity is required")
        self._require(draft["submitted_by"] == request["actor_id"], "forbidden", "only the submitter may submit this draft")
        if draft["status"] not in {"drafting", "submitted"}:
            self._require(False, "invalid_transition", "draft cannot be submitted in its current state")
        # ``submitted`` reaches here only on a retry: _mutate returns the stored
        # result when the operation row already exists, so an interrupted
        # submit (snapshot frozen, row missing) is the one way back in
        # (ai4-6qht). Re-freezing is safe because a review requires a
        # submitted_commit, which an interrupted submit never persisted.
        draft["status"] = "submitted"
        return draft, {"draft_id": draft["draft_id"], "status": "submitted"}

    def _review(self, docs, request):
        draft = copy.deepcopy(self._find(docs, request["draft_id"]))
        actor = request["actor_id"]
        self._require(bool(actor), "identity_required", "authenticated caller identity is required")
        self._authorize_namespace(draft["namespace"], actor)
        self._require(draft["status"] == "submitted" and bool(draft.get("submitted_commit")), "invalid_transition", "only a submitted snapshot may be reviewed")
        draft.update({"status": "accepted" if request["decision"] == "accept" else "rejected", "reviewer_id": actor,
                      "review_decided_at": _now(), "review_reason": request["reason"]})
        return draft, {"draft_id": draft["draft_id"], "status": draft["status"], "reviewer_id": actor}

    def _promote(self, docs, request):
        draft = copy.deepcopy(self._find(docs, request["draft_id"]))
        actor = request["actor_id"]
        self._require(bool(actor), "identity_required", "authenticated caller identity is required")
        self._require(draft["status"] == "accepted", "invalid_transition", "only an accepted draft may be promoted")
        self._authorize_namespace(draft["namespace"], actor)
        self._require(bool(request["candidate_id"].strip()) and bool(request["candidate_commit"].strip()), "invalid_candidate", "candidate ID and commit are required")
        draft.update({"status": "promoted", "promoted_candidate_id": request["candidate_id"], "promoted_candidate_commit": request["candidate_commit"]})
        return draft, {"draft_id": draft["draft_id"], "status": "promoted"}

    @staticmethod
    def _find(docs, draft_id):
        matches = [item for item in docs if item.get("@type") == "Draft" and item.get("draft_id") == draft_id]
        if len(matches) != 1:
            raise BufferError("draft_not_found", "draft was not found")
        return matches[0]

    def _authorize_namespace(self, namespace: str, actor_id: str) -> None:
        self._require(namespace in _NAMESPACES, "invalid_namespace", "unknown namespace")
        self._require(bool(actor_id), "identity_required", "authenticated caller identity is required")
        self._require(actor_id in self.reviewers.get(namespace, ()), "forbidden", "caller is not authorized for this namespace")

    @staticmethod
    def _require(condition: bool, code: str, message: str) -> None:
        if not condition:
            raise BufferError(code, message)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
