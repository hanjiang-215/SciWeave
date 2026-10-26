-- Minimal governance records required by the formal query slice.
-- Graph content stays in TerminusDB; this schema stores only identities and
-- the activation pointer that decides which formal revision is current.

CREATE TABLE IF NOT EXISTS mapping_submission (
    submission_id TEXT PRIMARY KEY,
    mapping_domain_id TEXT NOT NULL,
    submitter_id TEXT NOT NULL,
    base_formal_revision_id TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    content_digest TEXT NOT NULL,
    proposal_id TEXT NOT NULL UNIQUE,
    submitted_at TEXT NOT NULL,
    status TEXT NOT NULL,
    UNIQUE (mapping_domain_id, submission_id)
);

CREATE TABLE IF NOT EXISTS mapping_proposal (
    proposal_id TEXT PRIMARY KEY,
    mapping_domain_id TEXT NOT NULL,
    base_formal_revision_id TEXT,
    candidate_store_id TEXT,
    candidate_branch_id TEXT,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mapping_candidate_commit (
    candidate_commit_id TEXT PRIMARY KEY,
    mapping_domain_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    terminus_store_id TEXT NOT NULL,
    branch_id TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    base_formal_revision_id TEXT,
    content_digest TEXT NOT NULL,
    candidate_snapshot_digest TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (terminus_store_id, commit_hash),
    FOREIGN KEY (proposal_id) REFERENCES mapping_proposal(proposal_id)
);

CREATE TABLE IF NOT EXISTS mapping_audit_event (
    event_id TEXT PRIMARY KEY,
    mapping_domain_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    target_object_type TEXT NOT NULL,
    target_object_id TEXT NOT NULL,
    result TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    submission_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    candidate_commit_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS mapping_submission_idempotency
    ON mapping_submission(mapping_domain_id, submitter_id, idempotency_key);

CREATE TABLE IF NOT EXISTS mapping_review_attempt (
    attempt_id TEXT PRIMARY KEY,
    proposal_id TEXT,
    requested_base_formal_revision_id TEXT,
    requested_candidate_head_commit_hash TEXT,
    result_code TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mapping_review_preview (
    preview_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL UNIQUE,
    proposal_id TEXT NOT NULL,
    mapping_domain_id TEXT NOT NULL,
    base_formal_revision_id TEXT NOT NULL,
    candidate_commit_id TEXT NOT NULL,
    candidate_head_commit_hash TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (proposal_id, base_formal_revision_id, candidate_head_commit_hash),
    FOREIGN KEY (proposal_id) REFERENCES mapping_proposal(proposal_id),
    FOREIGN KEY (candidate_commit_id) REFERENCES mapping_candidate_commit(candidate_commit_id)
);

CREATE TABLE IF NOT EXISTS mapping_merge_request_buffer (
    buffer_id TEXT PRIMARY KEY,
    preview_id TEXT NOT NULL UNIQUE,
    proposal_id TEXT NOT NULL,
    mapping_domain_id TEXT NOT NULL,
    base_formal_revision_id TEXT NOT NULL,
    candidate_commit_id TEXT NOT NULL,
    candidate_head_commit_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (preview_id) REFERENCES mapping_review_preview(preview_id),
    FOREIGN KEY (proposal_id) REFERENCES mapping_proposal(proposal_id),
    FOREIGN KEY (candidate_commit_id) REFERENCES mapping_candidate_commit(candidate_commit_id)
);

CREATE TABLE IF NOT EXISTS mapping_review_event (
    event_id TEXT PRIMARY KEY,
    buffer_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (buffer_id) REFERENCES mapping_merge_request_buffer(buffer_id)
);

CREATE TABLE IF NOT EXISTS formal_mapping_revision (
    formal_revision_id TEXT PRIMARY KEY,
    mapping_domain_id TEXT NOT NULL,
    terminus_store_id TEXT NOT NULL,
    formal_branch_id TEXT NOT NULL,
    formal_commit_hash TEXT NOT NULL,
    base_formal_revision_id TEXT,
    source_proposal_id TEXT,
    approval_audit_event_id TEXT,
    published_by TEXT NOT NULL,
    published_at TEXT NOT NULL,
    graph_snapshot_digest TEXT,
    node_count INTEGER,
    edge_count INTEGER,
    FOREIGN KEY (base_formal_revision_id)
        REFERENCES formal_mapping_revision (formal_revision_id)
);

CREATE INDEX IF NOT EXISTS formal_mapping_revision_domain
    ON formal_mapping_revision (mapping_domain_id);

CREATE TABLE IF NOT EXISTS mapping_formalization_result (
    result_id TEXT PRIMARY KEY,
    mapping_domain_id TEXT NOT NULL,
    formalization_operation_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    result_status TEXT NOT NULL,
    formal_revision_id TEXT NOT NULL,
    terminus_store_id TEXT NOT NULL,
    formal_commit_hash TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (formal_revision_id)
        REFERENCES formal_mapping_revision (formal_revision_id)
);

CREATE TABLE IF NOT EXISTS mapping_candidate_disposition (
    candidate_commit_id TEXT PRIMARY KEY,
    disposition TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (candidate_commit_id) REFERENCES mapping_candidate_commit(candidate_commit_id)
);

CREATE TABLE IF NOT EXISTS mapping_formalization_attempt (
    result_id TEXT PRIMARY KEY,
    formalization_operation_id TEXT NOT NULL,
    merge_request_id TEXT NOT NULL,
    mapping_domain_id TEXT NOT NULL,
    base_formal_revision_id TEXT NOT NULL,
    candidate_head_commit_hash TEXT NOT NULL,
    approval_event_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    result_status TEXT NOT NULL CHECK (result_status IN (
        'requested', 'in_progress', 'graph_ready', 'reconciliation_required', 'succeeded', 'failed'
    )),
    reason TEXT,
    formal_revision_id TEXT,
    terminus_store_id TEXT,
    formal_branch_id TEXT,
    formal_commit_hash TEXT,
    recorded_at TEXT NOT NULL,
    UNIQUE (formalization_operation_id, attempt_number)
);

CREATE TABLE IF NOT EXISTS mapping_formalization_event (
    event_id TEXT PRIMARY KEY,
    formalization_operation_id TEXT NOT NULL,
    result_id TEXT NOT NULL,
    mapping_domain_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    result TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    details_json TEXT NOT NULL,
    FOREIGN KEY (result_id) REFERENCES mapping_formalization_attempt(result_id)
);

CREATE TABLE IF NOT EXISTS mapping_notification (
    notification_id TEXT PRIMARY KEY,
    formalization_operation_id TEXT NOT NULL,
    formal_revision_id TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (formal_revision_id) REFERENCES formal_mapping_revision(formal_revision_id)
);

CREATE INDEX IF NOT EXISTS mapping_formalization_result_lookup
    ON mapping_formalization_result
    (mapping_domain_id, formal_revision_id, result_status);

CREATE TABLE IF NOT EXISTS mapping_current_formal_revision (
    mapping_domain_id TEXT PRIMARY KEY,
    current_formal_revision_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (current_formal_revision_id)
        REFERENCES formal_mapping_revision (formal_revision_id)
);

-- Centre Agent prereview report log (ai4-oz3s): append-only, unique per
-- (candidate_id, candidate_head, rule_set_version, base_formal_revision_id).
-- SQLite never edits a report row; invalidation is expressed by appended
-- decision rows. The base revision is part of the key because a re-review
-- after ``base_moved`` judges the same head against a different base and must
-- append a new report instead of colliding with the invalidated one
-- (ai4-sf8l).
CREATE TABLE IF NOT EXISTS mapping_prereview_report (
    report_id               TEXT PRIMARY KEY,
    candidate_id            TEXT NOT NULL,
    candidate_head          TEXT NOT NULL,
    base_formal_revision_id TEXT NOT NULL DEFAULT '',
    rule_set_version        TEXT NOT NULL,
    checks                  TEXT NOT NULL,
    verdict                 TEXT NOT NULL CHECK (verdict IN ('passed', 'failed')),
    conflict_matrix         TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    UNIQUE (candidate_id, candidate_head, rule_set_version, base_formal_revision_id)
);

CREATE TABLE IF NOT EXISTS mapping_prereview_report_decision (
    decision_id           TEXT PRIMARY KEY,
    target_report_id      TEXT NOT NULL,
    reason                TEXT NOT NULL CHECK (reason IN ('head_moved', 'base_moved')),
    superseding_report_id TEXT,
    decided_at            TEXT NOT NULL,
    CHECK (reason <> 'head_moved' OR superseding_report_id IS NOT NULL),
    FOREIGN KEY (target_report_id) REFERENCES mapping_prereview_report (report_id),
    FOREIGN KEY (superseding_report_id) REFERENCES mapping_prereview_report (report_id)
);
