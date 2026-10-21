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
