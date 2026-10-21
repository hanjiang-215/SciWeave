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
    result_status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS wiki_formalization_result_lookup
    ON wiki_formalization_result (wiki_domain_id, formal_wiki_revision_id, result_status);

CREATE TABLE IF NOT EXISTS wiki_current_formal_revision (
    wiki_domain_id TEXT PRIMARY KEY,
    current_formal_revision_id TEXT
);
