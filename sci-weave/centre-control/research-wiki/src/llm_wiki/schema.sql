-- Append-only resource qualification records and their audit trail.
-- ResourceVersion content stays in TerminusDB; SQLite stores decisions only.

CREATE TABLE IF NOT EXISTS resource_version_review (
    review_id TEXT PRIMARY KEY,
    resource_version_id TEXT NOT NULL,
    target_owner_id TEXT,
    reviewer_id TEXT NOT NULL,
    authority_reference TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected', 'revoked')),
    reason TEXT NOT NULL,
    evidence_reference TEXT,
    decided_at TEXT NOT NULL,
    use_scope TEXT NOT NULL DEFAULT '[]',
    limitations TEXT NOT NULL DEFAULT '[]',
    content_digest TEXT,
    snapshot_digest TEXT,
    unknown_facts TEXT NOT NULL DEFAULT '[]',
    snapshot_status TEXT NOT NULL,
    target_location TEXT
);

CREATE INDEX IF NOT EXISTS resource_version_review_target
    ON resource_version_review (resource_version_id, decided_at);

CREATE TABLE IF NOT EXISTS wiki_audit_event (
    audit_event_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    detail TEXT,
    related_review_id TEXT
);

CREATE INDEX IF NOT EXISTS wiki_audit_event_target
    ON wiki_audit_event (target_id, occurred_at);

-- Candidate governance records. Wiki content snapshots remain in TerminusDB.
CREATE TABLE IF NOT EXISTS wiki_buffer_submission (
    submission_id TEXT PRIMARY KEY,
    wiki_domain_id TEXT NOT NULL,
    submitter_id TEXT NOT NULL,
    base_formal_revision_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    content_digest TEXT NOT NULL,
    proposal_id TEXT NOT NULL UNIQUE,
    submitted_at TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wiki_proposal (
    proposal_id TEXT PRIMARY KEY,
    wiki_domain_id TEXT NOT NULL,
    base_formal_revision_id TEXT NOT NULL,
    candidate_store_id TEXT NOT NULL,
    candidate_branch_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wiki_candidate_commit (
    candidate_commit_id TEXT PRIMARY KEY,
    wiki_domain_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL UNIQUE,
    terminus_store_id TEXT NOT NULL,
    branch_id TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    base_formal_revision_id TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    candidate_snapshot_digest TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS wiki_buffer_submission_domain
    ON wiki_buffer_submission (wiki_domain_id, submitted_at);

-- Formal activation facts only; Wiki content remains in TerminusDB.
CREATE TABLE IF NOT EXISTS formal_wiki_revision (
    formal_wiki_revision_id TEXT PRIMARY KEY,
    wiki_domain_id TEXT NOT NULL,
    terminus_store_id TEXT NOT NULL,
    formal_branch_id TEXT NOT NULL,
    formal_commit_hash TEXT NOT NULL,
    content_snapshot_digest TEXT
);

CREATE TABLE IF NOT EXISTS wiki_formalization_result (
    result_id TEXT PRIMARY KEY,
    wiki_domain_id TEXT NOT NULL,
    formal_wiki_revision_id TEXT NOT NULL,
    terminus_store_id TEXT NOT NULL,
    formal_commit_hash TEXT NOT NULL,
    result_status TEXT NOT NULL,
    resource_approval_map TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS wiki_formalization_result_lookup
    ON wiki_formalization_result (wiki_domain_id, formal_wiki_revision_id, result_status);

CREATE TABLE IF NOT EXISTS wiki_current_formal_revision (
    wiki_domain_id TEXT PRIMARY KEY,
    current_formal_revision_id TEXT
);

CREATE TABLE IF NOT EXISTS wiki_merge_request_buffer (
    merge_request_id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL, wiki_domain_id TEXT NOT NULL,
    base_formal_revision_id TEXT NOT NULL, candidate_head TEXT NOT NULL, candidate_commit_id TEXT NOT NULL,
    status TEXT NOT NULL, reviewer_id TEXT NOT NULL, owner_id TEXT, owner_decision TEXT NOT NULL,
    owner_event_id TEXT, created_at TEXT NOT NULL, locked_preview_id TEXT,
    owner_resource_approval_ids TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS wiki_review_evidence (
    preview_id TEXT PRIMARY KEY, merge_request_id TEXT NOT NULL, evidence_json TEXT NOT NULL,
    outcome TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wiki_formalization_operation (
    operation_id TEXT PRIMARY KEY, merge_request_id TEXT NOT NULL, state TEXT NOT NULL,
    attempt_number INTEGER NOT NULL, formal_revision_id TEXT, store_id TEXT, branch_id TEXT,
    commit_hash TEXT, reason_code TEXT, resource_approval_ids TEXT NOT NULL DEFAULT '[]',
    owner_event_id TEXT, candidate_head TEXT, base_formal_revision_id TEXT,
    notification_status TEXT NOT NULL DEFAULT 'not_sent', notification_reason TEXT,
    updated_at TEXT NOT NULL
);

-- Centre Agent prereview report log (ai4-oz3s): append-only, unique per
-- (proposal_id, candidate_head, rule_set_version). SQLite never edits a
-- report row; invalidation is expressed by appended decision rows.
CREATE TABLE IF NOT EXISTS wiki_prereview_report (
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

CREATE TABLE IF NOT EXISTS wiki_prereview_report_decision (
    decision_id           TEXT PRIMARY KEY,
    target_report_id      TEXT NOT NULL,
    reason                TEXT NOT NULL CHECK (reason IN ('head_moved', 'base_moved')),
    superseding_report_id TEXT,
    decided_at            TEXT NOT NULL,
    CHECK (reason <> 'head_moved' OR superseding_report_id IS NOT NULL),
    FOREIGN KEY (target_report_id) REFERENCES wiki_prereview_report (report_id),
    FOREIGN KEY (superseding_report_id) REFERENCES wiki_prereview_report (report_id)
);
