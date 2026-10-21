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
