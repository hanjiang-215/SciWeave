from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .canonical import sha256_json
from .domain import SNAPSHOT_CONFIRMED
from .sqlite_store import SqliteStore
from .terminus_store import ExactSnapshotStore


@dataclass(frozen=True)
class ReviewPreview:
    status: str
    reason_code: str | None = None
    preview_id: str | None = None
    evidence_id: str | None = None
    changes: tuple[dict[str, Any], ...] = ()
    affected_objects: tuple[str, ...] = ()
    route_impact: str = "unchanged"


@dataclass(frozen=True)
class MergeRequestBuffer:
    buffer_id: str
    preview_id: str
    proposal_id: str
    base_formal_revision_id: str
    candidate_commit_hash: str


@dataclass(frozen=True)
class ReviewDecision:
    event_id: str
    buffer_id: str
    actor_id: str
    decision: str
    reason: str
    occurred_at: str


class MappingReviewService:
    """Build immutable review evidence and fixed-head merge request buffers."""

    def __init__(self, sqlite: SqliteStore, terminus: ExactSnapshotStore, *, terminus_database: str):
        self.sqlite = sqlite
        self.terminus = terminus
        self.terminus_database = terminus_database

    def _failure(self, proposal_id: str, base_id: str, candidate_head: str, reason: str) -> ReviewPreview:
        with self.sqlite.connection() as db:
            db.execute(
                "INSERT INTO mapping_review_attempt VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), proposal_id, base_id, candidate_head, reason, _utc_now()),
            )
            db.commit()
        return ReviewPreview("unavailable", reason)

    def preview(self, proposal_id: str, base_formal_revision_id: str, candidate_head: str) -> ReviewPreview:
        with self.sqlite.connection() as db:
            proposal = db.execute("SELECT * FROM mapping_proposal WHERE proposal_id=?", (proposal_id,)).fetchone()
            candidate = db.execute(
                "SELECT * FROM mapping_candidate_commit WHERE proposal_id=? ORDER BY created_at DESC LIMIT 1",
                (proposal_id,),
            ).fetchone()
            if proposal is None or candidate is None:
                return self._failure(proposal_id, base_formal_revision_id, candidate_head, "candidate_mismatch")
            current = db.execute(
                "SELECT current_formal_revision_id FROM mapping_current_formal_revision WHERE mapping_domain_id=?",
                (proposal["mapping_domain_id"],),
            ).fetchone()
            revision = db.execute(
                "SELECT * FROM formal_mapping_revision WHERE formal_revision_id=?", (base_formal_revision_id,)
            ).fetchone()

        if current is None or current["current_formal_revision_id"] != base_formal_revision_id:
            return self._failure(proposal_id, base_formal_revision_id, candidate_head, "stale_base")
        if (proposal["base_formal_revision_id"] != base_formal_revision_id
                or candidate["base_formal_revision_id"] != base_formal_revision_id
                or candidate_head != candidate["commit_hash"]
                or proposal["candidate_store_id"] != candidate["terminus_store_id"]
                or proposal["candidate_branch_id"] != candidate["branch_id"]):
            return self._failure(proposal_id, base_formal_revision_id, candidate_head, "candidate_mismatch")
        if revision is None or revision["mapping_domain_id"] != proposal["mapping_domain_id"]:
            return self._failure(proposal_id, base_formal_revision_id, candidate_head, "stale_base")

        try:
            current_candidate_head = self.terminus.current_branch_head(
                candidate["terminus_store_id"], self.terminus_database, candidate["branch_id"]
            )
        except Exception:
            return self._failure(proposal_id, base_formal_revision_id, candidate_head, "candidate_unavailable")
        if current_candidate_head is None:
            return self._failure(proposal_id, base_formal_revision_id, candidate_head, "candidate_unavailable")
        if current_candidate_head != candidate_head:
            return self._failure(proposal_id, base_formal_revision_id, candidate_head, "candidate_mismatch")

        base = self.terminus.read_exact_snapshot(
            revision["terminus_store_id"], self.terminus_database,
            revision["formal_branch_id"], revision["formal_commit_hash"],
        )
        candidate_snapshot = self.terminus.read_exact_snapshot(
            candidate["terminus_store_id"], self.terminus_database,
            candidate["branch_id"], candidate_head,
        )
        if base.status != SNAPSHOT_CONFIRMED:
            return self._failure(proposal_id, base_formal_revision_id, candidate_head, "preview_unavailable")
        if candidate_snapshot.status != SNAPSHOT_CONFIRMED:
            return self._failure(proposal_id, base_formal_revision_id, candidate_head, "candidate_unavailable")
        if (base.store_id != revision["terminus_store_id"] or base.database != self.terminus_database
                or base.branch_id != revision["formal_branch_id"] or base.commit_hash != revision["formal_commit_hash"]):
            return self._failure(proposal_id, base_formal_revision_id, candidate_head, "preview_unavailable")
        if (candidate_snapshot.store_id != candidate["terminus_store_id"]
                or candidate_snapshot.database != self.terminus_database
                or candidate_snapshot.branch_id != candidate["branch_id"]
                or candidate_snapshot.commit_hash != candidate_head):
            return self._failure(proposal_id, base_formal_revision_id, candidate_head, "candidate_unavailable")

        if not _documents_are_well_formed(base.documents) or not _documents_are_well_formed(candidate_snapshot.documents):
            return self._failure(proposal_id, base_formal_revision_id, candidate_head, "preview_unavailable")
        changes = _diff(base.documents, candidate_snapshot.documents)
        affected = tuple(sorted({change["object_id"] for change in changes}))
        route_impact = "changed" if any(
            change["object_type"] in {"TaskNode", "DependencyEdge"} or _route_field(change["field"])
            for change in changes
        ) else "unchanged"
        identity = {
            "proposal_id": proposal_id,
            "base_formal_revision_id": base_formal_revision_id,
            "candidate_head": candidate_head,
            "base_digest": base.content_digest,
            "candidate_digest": candidate_snapshot.content_digest,
        }
        evidence_id = "evidence-" + sha256_json({"identity": identity, "changes": changes})
        preview_id = "preview-" + sha256_json(identity)
        evidence = {
            "changes": [
                {"object_type": item["object_type"], "object_id": item["object_id"], "field": item["field"],
                 "before_digest": sha256_json(item["before"]), "after_digest": sha256_json(item["after"])}
                for item in changes
            ],
            "affected_objects": affected,
            "route_impact": route_impact,
        }
        with self.sqlite.connection() as db:
            latest = db.execute(
                "SELECT current_formal_revision_id FROM mapping_current_formal_revision WHERE mapping_domain_id=?",
                (proposal["mapping_domain_id"],),
            ).fetchone()
            if latest is None or latest["current_formal_revision_id"] != base_formal_revision_id:
                db.execute(
                    "INSERT INTO mapping_review_attempt VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), proposal_id, base_formal_revision_id, candidate_head,
                     "stale_base", _utc_now()),
                )
                db.commit()
                return ReviewPreview("unavailable", "stale_base")
            db.execute(
                """INSERT OR IGNORE INTO mapping_review_preview
                (preview_id,evidence_id,proposal_id,mapping_domain_id,base_formal_revision_id,
                 candidate_commit_id,candidate_head_commit_hash,evidence_json,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (preview_id, evidence_id, proposal_id, proposal["mapping_domain_id"], base_formal_revision_id,
                 candidate["candidate_commit_id"], candidate_head, json.dumps(evidence, sort_keys=True), _utc_now()),
            )
            row = db.execute("SELECT * FROM mapping_review_preview WHERE preview_id=?", (preview_id,)).fetchone()
            if row is None or row["evidence_id"] != evidence_id or row["evidence_json"] != json.dumps(evidence, sort_keys=True):
                return self._failure(proposal_id, base_formal_revision_id, candidate_head, "preview_unavailable")
            db.commit()
        return ReviewPreview("available", preview_id=preview_id, evidence_id=evidence_id,
                             changes=tuple(changes), affected_objects=affected, route_impact=route_impact)

    def create_buffer(self, preview_id: str) -> MergeRequestBuffer:
        with self.sqlite.connection() as db:
            preview = db.execute("SELECT * FROM mapping_review_preview WHERE preview_id=?", (preview_id,)).fetchone()
            if preview is None:
                raise ValueError("preview_unavailable")
            current = db.execute(
                "SELECT current_formal_revision_id FROM mapping_current_formal_revision WHERE mapping_domain_id=?",
                (preview["mapping_domain_id"],),
            ).fetchone()
            candidate = db.execute(
                "SELECT * FROM mapping_candidate_commit WHERE candidate_commit_id=?", (preview["candidate_commit_id"],)
            ).fetchone()
            proposal = db.execute("SELECT * FROM mapping_proposal WHERE proposal_id=?", (preview["proposal_id"],)).fetchone()
            if current is None or current["current_formal_revision_id"] != preview["base_formal_revision_id"]:
                raise ValueError("stale_base")
            if (candidate is None or proposal is None or candidate["commit_hash"] != preview["candidate_head_commit_hash"]
                    or candidate["base_formal_revision_id"] != preview["base_formal_revision_id"]
                    or proposal["base_formal_revision_id"] != preview["base_formal_revision_id"]):
                raise ValueError("candidate_mismatch")
            try:
                current_head = self.terminus.current_branch_head(
                    candidate["terminus_store_id"], self.terminus_database, candidate["branch_id"]
                )
            except Exception as error:
                self._failure(
                    preview["proposal_id"], preview["base_formal_revision_id"],
                    preview["candidate_head_commit_hash"], "candidate_unavailable",
                )
                raise ValueError("candidate_unavailable") from error
            if current_head is None:
                raise ValueError("candidate_unavailable")
            if current_head != preview["candidate_head_commit_hash"]:
                raise ValueError("candidate_mismatch")
            buffer_id = "buffer-" + sha256_json({"preview_id": preview_id})
            db.execute(
                """INSERT OR IGNORE INTO mapping_merge_request_buffer
                (buffer_id,preview_id,proposal_id,mapping_domain_id,base_formal_revision_id,
                 candidate_commit_id,candidate_head_commit_hash,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (buffer_id, preview_id, preview["proposal_id"], preview["mapping_domain_id"],
                 preview["base_formal_revision_id"], preview["candidate_commit_id"],
                 preview["candidate_head_commit_hash"], "pending", _utc_now()),
            )
            row = db.execute("SELECT * FROM mapping_merge_request_buffer WHERE preview_id=?", (preview_id,)).fetchone()
            db.commit()
        return MergeRequestBuffer(row["buffer_id"], row["preview_id"], row["proposal_id"],
                                  row["base_formal_revision_id"], row["candidate_head_commit_hash"])

    def record_review(self, buffer_id: str, actor_id: str, decision: str, reason: str) -> ReviewDecision:
        allowed = {"approved", "returned", "rejected"}
        if not actor_id or decision not in allowed or not reason.strip():
            raise ValueError("review requires actor, a supported decision, and reason")
        event_id, occurred_at = str(uuid.uuid4()), _utc_now()
        with self.sqlite.connection() as db:
            if db.execute("SELECT 1 FROM mapping_merge_request_buffer WHERE buffer_id=?", (buffer_id,)).fetchone() is None:
                raise ValueError("buffer_unavailable")
            db.execute(
                "INSERT INTO mapping_review_event VALUES (?,?,?,?,?,?)",
                (event_id, buffer_id, actor_id, decision, reason.strip(), occurred_at),
            )
            db.commit()
        return ReviewDecision(event_id, buffer_id, actor_id, decision, reason.strip(), occurred_at)


def _documents_are_well_formed(documents) -> bool:
    seen = set()
    for document in documents:
        object_id = document.get("@id")
        object_type = document.get("@type")
        if not isinstance(object_id, str) or not object_id or object_id in seen:
            return False
        if not isinstance(object_type, str) or not object_type:
            return False
        seen.add(object_id)
    return True


def _diff(before_documents, after_documents):
    before = {doc.get("@id"): doc for doc in before_documents if isinstance(doc.get("@id"), str)}
    after = {doc.get("@id"): doc for doc in after_documents if isinstance(doc.get("@id"), str)}
    result = []
    for object_id in sorted(set(before) | set(after)):
        left, right = before.get(object_id), after.get(object_id)
        keys = set(left or {}) | set(right or {})
        # Lifecycle labels describe the governance view, not graph content.
        keys.discard("lifecycle_state")
        for field in sorted(keys):
            old, new = (left or {}).get(field), (right or {}).get(field)
            if old != new:
                object_type = str((right or left or {}).get("@type", "Unknown")).rsplit("/", 1)[-1]
                result.append({"object_type": object_type, "object_id": object_id,
                               "field": field, "before": old, "after": new})
    return result


def _route_field(field: str) -> bool:
    lowered = field.lower()
    return any(token in lowered for token in ("route", "activation", "condition", "input", "output"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
