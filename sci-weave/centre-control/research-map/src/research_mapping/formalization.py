from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .canonical import sha256_json
from .domain import FormalMappingRevision, SNAPSHOT_CONFIRMED, SnapshotRead
from .sqlite_store import SqliteStore


class FormalSnapshotStore(Protocol):
    def current_branch_head(self, store_id: str, database: str, branch_id: str) -> str | None: ...

    def create_formal_snapshot(
        self, store_id: str, database: str, branch_id: str, commit_hash: str, operation_id: str
    ) -> SnapshotRead: ...


@dataclass(frozen=True)
class FormalizationOutcome:
    status: str
    formalization_operation_id: str
    result_id: str | None = None
    formal_revision_id: str | None = None
    reason_code: str | None = None
    attempt_number: int | None = None
    #: The mapping domain this formalization belongs to, taken from the persisted
    #: candidate/attempt facts. Present on ``succeeded`` outcomes so the caller can
    #: publish ``formal_revision_published`` with the correct domain even when the
    #: optional ``mapping_domain_id`` tool argument was not supplied.
    mapping_domain_id: str | None = None


class MappingFormalizationService:
    """Promote an Owner-approved immutable candidate through an atomic SQLite activation."""

    def __init__(self, sqlite: SqliteStore, terminus: FormalSnapshotStore, *, terminus_database: str,
                 is_project_owner):
        self.sqlite = sqlite
        self.terminus = terminus
        self.terminus_database = terminus_database
        self.is_project_owner = is_project_owner

    def reconcile(self, operation_id: str) -> FormalizationOutcome:
        """Resume the same operation identity; never invent a new Commit or revision."""
        with self.sqlite.connection() as db:
            row = db.execute(
                "SELECT merge_request_id FROM mapping_formalization_attempt "
                "WHERE formalization_operation_id=? ORDER BY attempt_number DESC LIMIT 1",
                (operation_id,),
            ).fetchone()
        if row is None:
            return FormalizationOutcome("reconciliation_required", operation_id,
                                        reason_code="operation_not_found")
        return self.formalize(row["merge_request_id"], operation_id)

    def record_notification_result(self, operation_id: str, *, delivered: bool, reason: str | None = None) -> None:
        """Record notification delivery separately from formal publication."""
        with self.sqlite.connection() as db:
            attempt = db.execute(
                "SELECT * FROM mapping_formalization_attempt WHERE formalization_operation_id=? "
                "AND result_status='succeeded' ORDER BY attempt_number DESC LIMIT 1", (operation_id,)
            ).fetchone()
            if attempt is None:
                raise ValueError("formalization_not_succeeded")
            notification = db.execute(
                "SELECT * FROM mapping_notification WHERE formalization_operation_id=? "
                "ORDER BY created_at DESC LIMIT 1", (operation_id,)
            ).fetchone()
            if notification is None:
                raise ValueError("notification_unavailable")
            status = "delivered" if delivered else "failed"
            db.execute("UPDATE mapping_notification SET status=?,reason=? WHERE notification_id=?",
                       (status, None if delivered else (reason or "delivery_failed"), notification["notification_id"]))
            db.execute(
                "INSERT INTO mapping_formalization_event VALUES (?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), operation_id, attempt["result_id"], attempt["mapping_domain_id"],
                 "mapping-notification-delivery", "notification_delivery", status, _utc_now(),
                 json.dumps({"reason": None if delivered else reason}, sort_keys=True)),
            )
            db.commit()

    def formalize(self, merge_request_id: str, operation_id: str) -> FormalizationOutcome:
        if not merge_request_id or not operation_id:
            raise ValueError("merge_request_id and operation_id are required")
        with self.sqlite.connection() as db:
            prior = db.execute(
                "SELECT * FROM mapping_formalization_attempt WHERE formalization_operation_id=? "
                "ORDER BY attempt_number DESC LIMIT 1", (operation_id,)
            ).fetchone()
            if prior and prior["result_status"] == "succeeded":
                if prior["merge_request_id"] != merge_request_id:
                    return FormalizationOutcome("reconciliation_required", operation_id,
                                                reason_code="operation_identity_mismatch")
                revision = db.execute(
                    "SELECT * FROM formal_mapping_revision WHERE formal_revision_id=?",
                    (prior["formal_revision_id"],),
                ).fetchone()
                result = db.execute(
                    "SELECT * FROM mapping_formalization_result WHERE result_id=? AND result_status='succeeded'",
                    (prior["result_id"],),
                ).fetchone()
                pointer = db.execute(
                    "SELECT current_formal_revision_id FROM mapping_current_formal_revision WHERE mapping_domain_id=?",
                    (prior["mapping_domain_id"],),
                ).fetchone()
                if (revision is None or result is None or pointer is None
                        or pointer["current_formal_revision_id"] != prior["formal_revision_id"]
                        or result["formal_revision_id"] != prior["formal_revision_id"]
                        or result["terminus_store_id"] != revision["terminus_store_id"]
                        or result["formal_commit_hash"] != revision["formal_commit_hash"]):
                    return FormalizationOutcome("reconciliation_required", operation_id, prior["result_id"],
                                                reason_code="activation_evidence_mismatch")
                exact = self.terminus.read_exact_snapshot(
                    revision["terminus_store_id"], self.terminus_database,
                    revision["formal_branch_id"], revision["formal_commit_hash"],
                )
                if (exact.status != SNAPSHOT_CONFIRMED
                        or exact.content_digest != revision["graph_snapshot_digest"]
                        or exact.store_id != revision["terminus_store_id"]
                        or exact.branch_id != revision["formal_branch_id"]
                        or exact.commit_hash != revision["formal_commit_hash"]):
                    return FormalizationOutcome("reconciliation_required", operation_id, prior["result_id"],
                                                reason_code="formal_snapshot_reconciliation_required")
                return FormalizationOutcome("succeeded", operation_id, prior["result_id"],
                                            prior["formal_revision_id"], attempt_number=prior["attempt_number"],
                                            mapping_domain_id=prior["mapping_domain_id"])
            else:
                committed_ref = None
            details = db.execute(
                """SELECT b.*,p.mapping_domain_id,p.status AS proposal_status,
                          c.terminus_store_id,c.branch_id,c.commit_hash,c.base_formal_revision_id AS candidate_base,
                          c.candidate_commit_id,r.formal_branch_id,r.formal_commit_hash
                   FROM mapping_merge_request_buffer b
                   JOIN mapping_proposal p ON p.proposal_id=b.proposal_id
                   JOIN mapping_candidate_commit c ON c.candidate_commit_id=b.candidate_commit_id
                   JOIN formal_mapping_revision r ON r.formal_revision_id=b.base_formal_revision_id
                   WHERE b.buffer_id=?""", (merge_request_id,)
            ).fetchone()
            approval = db.execute(
                "SELECT * FROM mapping_review_event WHERE buffer_id=? "
                "ORDER BY occurred_at DESC,rowid DESC LIMIT 1", (merge_request_id,)
            ).fetchone()
            current = None if details is None else db.execute(
                "SELECT current_formal_revision_id FROM mapping_current_formal_revision WHERE mapping_domain_id=?",
                (details["mapping_domain_id"],),
            ).fetchone()
            owner_ok = bool(
                approval and approval["decision"] == "approved"
                and self.is_project_owner(approval["actor_id"], details["mapping_domain_id"])
            ) if details else False
            reason = None
            if details is None:
                reason = "merge_request_unavailable"
            elif not owner_ok:
                reason = "owner_approval_required"
            elif (details["status"] != "pending" or details["proposal_status"] not in {"candidate", "candidate_created"}
                  or details["candidate_head_commit_hash"] != details["commit_hash"]
                  or details["base_formal_revision_id"] != details["candidate_base"]):
                reason = "candidate_mismatch"
            elif current is None or current["current_formal_revision_id"] != details["base_formal_revision_id"]:
                reason = "stale_base"
            if prior:
                if prior["merge_request_id"] != merge_request_id or (details and (
                    prior["mapping_domain_id"] != details["mapping_domain_id"]
                    or prior["base_formal_revision_id"] != details["base_formal_revision_id"]
                    or prior["candidate_head_commit_hash"] != details["candidate_head_commit_hash"]
                    or (approval and prior["approval_event_id"] != approval["event_id"])
                )):
                    return FormalizationOutcome("reconciliation_required", operation_id,
                                                prior["result_id"], reason_code="operation_identity_mismatch")
            attempt_no = 1 if prior is None else int(prior["attempt_number"]) + 1
            result_id = str(uuid.uuid4())
            actor_id = "mapping-formalization-service"
            if reason:
                self._record_attempt(result_id, operation_id, merge_request_id, details, approval,
                                     attempt_no, "failed", reason, actor_id)
                return FormalizationOutcome("failed", operation_id, result_id, reason_code=reason,
                                            attempt_number=attempt_no)
            assert details is not None and approval is not None
        try:
            current_head = self.terminus.current_branch_head(
                details["terminus_store_id"], self.terminus_database, details["branch_id"]
            )
        except (OSError, TimeoutError, RuntimeError):
            current_head = None
        if current_head is None:
            reason = "candidate_unavailable"
            self._record_attempt(result_id, operation_id, merge_request_id, details, approval,
                                 attempt_no, "reconciliation_required", reason, actor_id)
            return FormalizationOutcome("reconciliation_required", operation_id, result_id, reason_code=reason,
                                        attempt_number=attempt_no)
        if current_head != details["candidate_head_commit_hash"]:
            reason = "candidate_mismatch"
            self._record_attempt(result_id, operation_id, merge_request_id, details, approval,
                                 attempt_no, "failed", reason, actor_id)
            return FormalizationOutcome("failed", operation_id, result_id, reason_code=reason,
                                        attempt_number=attempt_no)
        self._record_attempt(result_id, operation_id, merge_request_id, details, approval,
                             attempt_no, "in_progress", None, actor_id)

        try:
            snapshot = self.terminus.create_formal_snapshot(
                details["terminus_store_id"], self.terminus_database, details["branch_id"],
                details["candidate_head_commit_hash"], operation_id,
            )
        except (OSError, TimeoutError, RuntimeError, ValueError):
            snapshot = SnapshotRead.unavailable("formal_snapshot_result_unknown")
        if snapshot.status != SNAPSHOT_CONFIRMED or (
            snapshot.store_id != details["terminus_store_id"] or snapshot.database != self.terminus_database
            or snapshot.branch_id != details["branch_id"] or snapshot.commit_hash != details["candidate_head_commit_hash"]
        ):
            status = "reconciliation_required" if snapshot.status != "missing" else "failed"
            reason = snapshot.reason_code or "formal_snapshot_unconfirmed"
            self._set_attempt_status(result_id, status, reason, snapshot)
            return FormalizationOutcome(status, operation_id, result_id, reason_code=reason, attempt_number=attempt_no)
        # Read the exact immutable reference again before allowing SQLite activation.
        try:
            verified = self.terminus.read_exact_snapshot(
                details["terminus_store_id"], self.terminus_database, details["branch_id"],
                details["candidate_head_commit_hash"],
            )
        except (OSError, TimeoutError, RuntimeError, ValueError):
            verified = SnapshotRead.unavailable("formal_snapshot_readback_unknown")
        if verified.status != SNAPSHOT_CONFIRMED or verified.content_digest != snapshot.content_digest:
            reason = verified.reason_code or "formal_snapshot_readback_mismatch"
            self._set_attempt_status(result_id, "reconciliation_required", reason, verified)
            return FormalizationOutcome("reconciliation_required", operation_id, result_id,
                                        reason_code=reason, attempt_number=attempt_no)
        self._set_attempt_status(result_id, "graph_ready", None, snapshot)
        return self._activate(result_id, operation_id, merge_request_id, details, approval, snapshot, attempt_no)

    def _activation_is_committed(self, operation_id, result_id, revision_id, domain_id,
                                 store_id, branch_id, commit_hash, digest) -> bool:
        try:
            with self.sqlite.connection() as db:
                pointer = db.execute(
                    "SELECT current_formal_revision_id FROM mapping_current_formal_revision WHERE mapping_domain_id=?",
                    (domain_id,),
                ).fetchone()
                revision = db.execute(
                    "SELECT * FROM formal_mapping_revision WHERE formal_revision_id=?", (revision_id,)
                ).fetchone()
                result = db.execute(
                    "SELECT * FROM mapping_formalization_result WHERE result_id=? "
                    "AND formalization_operation_id=? AND result_status='succeeded'",
                    (result_id, operation_id),
                ).fetchone()
                attempt = db.execute(
                    "SELECT * FROM mapping_formalization_attempt WHERE result_id=?", (result_id,)
                ).fetchone()
            if (pointer is None or pointer["current_formal_revision_id"] != revision_id
                    or revision is None or result is None or attempt is None
                    or revision["terminus_store_id"] != store_id
                    or revision["formal_branch_id"] != branch_id
                    or revision["formal_commit_hash"] != commit_hash
                    or revision["graph_snapshot_digest"] != digest
                    or result["formal_revision_id"] != revision_id
                    or result["terminus_store_id"] != store_id
                    or result["formal_commit_hash"] != commit_hash
                    or attempt["result_status"] != "succeeded"):
                return False
            exact = self.terminus.read_exact_snapshot(store_id, self.terminus_database, branch_id, commit_hash)
            return (exact.status == SNAPSHOT_CONFIRMED and exact.content_digest == digest
                    and exact.store_id == store_id and exact.branch_id == branch_id
                    and exact.commit_hash == commit_hash)
        except (sqlite3.Error, OSError, TimeoutError, ValueError):
            return False

    def _record_attempt(self, result_id, operation_id, mr, details, approval, attempt_no, status, reason, actor):
        now = _utc_now()
        domain = details["mapping_domain_id"] if details else "unknown"
        base = details["base_formal_revision_id"] if details else "unknown"
        head = details["candidate_head_commit_hash"] if details else "unknown"
        approval_id = approval["event_id"] if approval else "missing"
        with self.sqlite.connection() as db:
            db.execute(
                """INSERT INTO mapping_formalization_attempt
                (result_id,formalization_operation_id,merge_request_id,mapping_domain_id,base_formal_revision_id,
                 candidate_head_commit_hash,approval_event_id,attempt_number,result_status,reason,recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (result_id, operation_id, mr, domain, base, head, approval_id, attempt_no, status, reason, now),
            )
            db.execute(
                "INSERT INTO mapping_formalization_event VALUES (?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), operation_id, result_id, domain, actor, "formalization_attempt", status,
                 now, json.dumps({"reason": reason, "merge_request_id": mr}, sort_keys=True)),
            )
            db.commit()

    def _set_attempt_status(self, result_id, status, reason, snapshot):
        now = _utc_now()
        with self.sqlite.connection() as db:
            db.execute(
                "UPDATE mapping_formalization_attempt SET result_status=?,reason=?,terminus_store_id=?,"
                "formal_branch_id=?,formal_commit_hash=?,recorded_at=? WHERE result_id=?",
                (status, reason, snapshot.store_id, snapshot.branch_id, snapshot.commit_hash, now, result_id),
            )
            db.commit()

    def _activate(self, result_id, operation_id, mr, details, approval, snapshot, attempt_no):
        now = _utc_now()
        revision_id = "formal-" + sha256_json({"operation_id": operation_id,
            "candidate_head": details["candidate_head_commit_hash"],
            "base": details["base_formal_revision_id"], "approval": approval["event_id"]})
        try:
            with self.sqlite.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    "SELECT current_formal_revision_id FROM mapping_current_formal_revision WHERE mapping_domain_id=?",
                    (details["mapping_domain_id"],),
                ).fetchone()
                if current is None or current["current_formal_revision_id"] != details["base_formal_revision_id"]:
                    raise RuntimeError("stale_base")
                revision = FormalMappingRevision(
                    revision_id, details["mapping_domain_id"], snapshot.store_id, snapshot.branch_id,
                    snapshot.commit_hash, details["base_formal_revision_id"], details["proposal_id"],
                    approval["event_id"], approval["actor_id"], now, snapshot.content_digest,
                    sum(str(d.get("@type", "")).endswith("TaskNode") for d in snapshot.documents),
                    sum(str(d.get("@type", "")).endswith("DependencyEdge") for d in snapshot.documents),
                )
                db.execute(
                    """INSERT INTO formal_mapping_revision
                    (formal_revision_id,mapping_domain_id,terminus_store_id,formal_branch_id,formal_commit_hash,
                     base_formal_revision_id,source_proposal_id,approval_audit_event_id,published_by,published_at,
                     graph_snapshot_digest,node_count,edge_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (revision.formal_revision_id, revision.mapping_domain_id, revision.terminus_store_id,
                     revision.formal_branch_id, revision.formal_commit_hash, revision.base_formal_revision_id,
                     revision.source_proposal_id, revision.approval_audit_event_id, revision.published_by,
                     revision.published_at, revision.graph_snapshot_digest, revision.node_count, revision.edge_count),
                )
                updated = db.execute(
                    "UPDATE mapping_current_formal_revision SET current_formal_revision_id=?,updated_at=? "
                    "WHERE mapping_domain_id=? AND current_formal_revision_id=?",
                    (revision_id, now, details["mapping_domain_id"], details["base_formal_revision_id"]),
                ).rowcount
                if updated != 1:
                    raise RuntimeError("stale_base")
                db.execute(
                    "UPDATE mapping_formalization_attempt SET result_status='succeeded',formal_revision_id=?,"
                    "terminus_store_id=?,formal_branch_id=?,formal_commit_hash=?,recorded_at=? WHERE result_id=?",
                    (revision_id, snapshot.store_id, snapshot.branch_id, snapshot.commit_hash, now, result_id),
                )
                db.execute(
                    "INSERT INTO mapping_formalization_result VALUES (?,?,?,?,?,?,?,?,?)",
                    (result_id, details["mapping_domain_id"], operation_id, attempt_no, "succeeded", revision_id,
                     snapshot.store_id, snapshot.commit_hash, now),
                )
                db.execute("UPDATE mapping_merge_request_buffer SET status='merged' WHERE buffer_id=?", (mr,))
                db.execute("UPDATE mapping_proposal SET status='merged' WHERE proposal_id=?", (details["proposal_id"],))
                db.execute("""INSERT INTO mapping_candidate_disposition VALUES (?, 'formalized', ?) """,
                           (details["candidate_commit_id"], now))
                db.execute(
                    "INSERT INTO mapping_formalization_event VALUES (?,?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), operation_id, result_id, details["mapping_domain_id"],
                     "mapping-formalization-service", "formal_revision_activated", "succeeded", now,
                     json.dumps({"formal_revision_id": revision_id, "approval_event_id": approval["event_id"]}, sort_keys=True)),
                )
                db.execute(
                    "INSERT INTO mapping_notification VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), operation_id, revision_id, "pending", None, now),
                )
                db.commit()
        except (sqlite3.Error, RuntimeError) as error:
            # A commit call can raise after SQLite has durably committed. Inspect
            # persisted activation evidence before changing the attempt status.
            if self._activation_is_committed(
                operation_id, result_id, revision_id, details["mapping_domain_id"],
                snapshot.store_id, snapshot.branch_id, snapshot.commit_hash, snapshot.content_digest,
            ):
                return FormalizationOutcome("succeeded", operation_id, result_id, revision_id,
                                            attempt_number=attempt_no,
                                            mapping_domain_id=details["mapping_domain_id"])
            status, reason = "reconciliation_required", str(error) or "activation_outcome_unknown"
            self._set_attempt_status(result_id, status, reason, snapshot)
            return FormalizationOutcome(status, operation_id, result_id, reason_code=reason,
                                        attempt_number=attempt_no)
        return FormalizationOutcome("succeeded", operation_id, result_id, revision_id,
                                    attempt_number=attempt_no,
                                    mapping_domain_id=details["mapping_domain_id"])


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
