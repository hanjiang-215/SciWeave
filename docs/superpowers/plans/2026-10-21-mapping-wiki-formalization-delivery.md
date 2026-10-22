# Research Mapping and LLM-Wiki Formalization Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Mapping and Wiki candidate-to-formalization implementation slices, including stable retries, exact Commit verification, atomic activation, audit, and recovery.

**Architecture:** Keep Research Mapping and LLM-Wiki as separate Python projects with independent SQLite governance and TerminusDB stores. Execute each ticket in dependency order, using application services behind existing store seams; only a SQLite transaction activates a formal revision, and unknown cross-store outcomes require reconciliation rather than blind retry.

**Tech Stack:** Python >=3.11, `uv`, Python standard library (`sqlite3`, `unittest`, `urllib`), TerminusDB 12.0.8 integration service.

---

## Execution guardrails

- Before each ticket change, reread the current ticket and confirm the session identity against assignee, branch `feature/hanjiang`, and `git config user.name`; edit ticket content only as its assignee.
- Preserve pre-existing working changes. In particular, inspect `.tickets/ai4-6s53.md` before making any ticket update and retain its current content.
- Use TDD for every behavior: add one focused failing test, run it and confirm expected failure, implement minimal behavior, rerun focused and project suite.
- Never edit Mapping and Wiki storage/authentication behavior through a shared package. Their schema, services, location records, and audit events remain separate.
- For real-store tests, use unique temporary TerminusDB databases and clean them even on failure. Never use a fixed deployment port in source, tests, or docs.
- Do not claim integration validation when the integration suite is skipped. Do not add dependencies without a dependency ticket and project manifest/lock updates.

## Task 1: Finish Mapping candidate snapshot identity and recovery

**Files:**
- Modify: `sci-weave/centre-control/research-map/src/research_mapping/terminus_store.py`
- Modify: `sci-weave/centre-control/research-map/src/research_mapping/candidate_submission.py`
- Modify: `sci-weave/centre-control/research-map/src/research_mapping/sqlite_store.py`
- Modify: `sci-weave/centre-control/research-map/src/research_mapping/schema.sql`
- Test: `sci-weave/centre-control/research-map/tests/test_candidate_terminus_store.py`
- Test: `sci-weave/centre-control/research-map/tests/test_candidate_submission.py`
- Test: `sci-weave/centre-control/research-map/tests/test_terminus_integration.py`
- Update evidence: `.tickets/ai4-6s53.md` (assignee confirmation required)

- [ ] **Step 1: Add a failing adapter test for exact candidate confirmation.** Assert that confirmed candidate write returns its isolated branch and exact commit only after reading back matching base marker, idempotency identity, and canonical document snapshot; assert mismatch returns unknown/unavailable rather than success.
- [ ] **Step 2: Run the focused adapter test and verify the intended failure.**

Run: `uv run --locked python -m unittest tests.test_candidate_terminus_store -v`
Expected: the new test fails because the production adapter does not yet confirm candidate identity/content.

- [ ] **Step 3: Implement minimum candidate write/readback contract.** Use deterministic candidate branch identity derived from stable operation identity; create/reset from the exact base Commit; write an explicit operation/base/content marker with the candidate documents; read the candidate head and exact Commit snapshot back; only return confirmed when branch, base, marker, complete canonical payload, and commit identity match. Keep network outcome ambiguity structured.
- [ ] **Step 4: Add a failing service test for same-identity unknown-result reconciliation.** Simulate an uncertain first write and a later exact readback; verify retry returns the original candidate IDs/Commit and does not create a second logical Submission, Proposal, or CandidateCommit. Also cover unresolved identity remaining `result_unknown`.
- [ ] **Step 5: Run focused service tests and verify expected failures.**

Run: `uv run --locked python -m unittest tests.test_candidate_submission -v`
Expected: new reconciliation assertions fail before implementation.

- [ ] **Step 6: Implement service reconciliation and atomic governance persistence.** Reuse the same idempotency key and deterministic candidate identity; bind submitting actor, domain, base, submission ID, and canonical digest; on retry query/verify exact candidate marker and content before persisting records. Preserve immutable prior records and return `idempotency_conflict` for identity reuse with different content.
- [ ] **Step 7: Run Mapping unit suite.**

Run: `uv run --locked python -m unittest discover -s tests -v`
Expected: all unit tests pass; integration tests may be skipped locally but skips are not acceptance evidence.

- [ ] **Step 8: Add and run real TerminusDB candidate integration tests.** Verify fresh candidate isolation from formal base, exact historical-base reset, snapshot readback, same-identity replay, and cleanup of temporary database. Include deterministic assertions; do not rely on a fixed service port.

Run: `uv run --locked python -m unittest discover -s tests -p "test_terminus_integration.py" -v`
Expected: all enabled real-store cases pass without skips for this ticket's evidence.

- [ ] **Step 9: Record evidence in `ai4-6s53` and validate the mapping ticket graph.** Include exact commands, test counts, active service version, readback properties, and unresolved limitations. Run `fer dep cycle`; do not close until every acceptance criterion has evidence.

## Task 2: Implement Mapping candidate preview and review buffer

**Files:**
- Create: `sci-weave/centre-control/research-map/src/research_mapping/review.py`
- Modify: `sci-weave/centre-control/research-map/src/research_mapping/domain.py`
- Modify: `sci-weave/centre-control/research-map/src/research_mapping/sqlite_store.py`
- Modify: `sci-weave/centre-control/research-map/src/research_mapping/schema.sql`
- Test: `sci-weave/centre-control/research-map/tests/test_review.py`
- Test: `sci-weave/centre-control/research-map/tests/test_terminus_integration.py`
- Update evidence: `.tickets/ai4-z0lb.md` (assignee confirmation required)

- [ ] **Step 1: Add a failing test for a deterministic field-level candidate diff.** Use temporary SQLite and Fake TerminusStore snapshots for exact base and candidate commits; assert stable preview/evidence IDs, changed TaskNode/DependencyEdge fields, affected objects, and route impact summary.
- [ ] **Step 2: Run the new focused test and verify it fails because review service is absent.**

Run: `uv run --locked python -m unittest tests.test_review -v`
Expected: import or missing-service failure for the new API.

- [ ] **Step 3: Implement preview DTOs and diff service.** Require proposal, base FormalMappingRevision, exact base commit ref, candidate branch/head, and digest. Do not copy graph body to SQLite; persist only structured evidence and stable references.
- [ ] **Step 4: Add failing tests for stale base, wrong candidate head, unreadable snapshot, and incomplete diff.** Assert each returns a stable failure reason and cannot produce an approvable Merge Request Buffer; preserve prior preview evidence.
- [ ] **Step 5: Implement invalidation and audited failure records.** Before returning an effective preview or buffer, recheck current formal pointer and fixed candidate head. Distinguish stale base, candidate mismatch/unavailable, and preview unavailable.
- [ ] **Step 6: Add failing tests for Buffer locking and reviewer audit.** Assert Buffer references the exact Proposal, candidate head, base, preview/evidence, and records reviewer, UTC time, decision, and reason; do not treat this review as Project Owner formal approval.
- [ ] **Step 7: Implement buffer creation and review recording in SQLite transactions.** Keep candidate content immutable and out of SQLite.
- [ ] **Step 8: Run Mapping unit tests.**

Run: `uv run --locked python -m unittest discover -s tests -v`
Expected: all unit tests pass.

- [ ] **Step 9: Run exact-Commit integration tests for base/candidate readback.**

Run: `uv run --locked python -m unittest discover -s tests -p "test_terminus_integration.py" -v`
Expected: explicit real-store tests pass with no skip counted as evidence.

- [ ] **Step 10: Record `ai4-z0lb` verification and check dependencies.** Run `fer dep cycle`; retain ticket open if any acceptance item lacks evidence.

## Task 3: Implement Mapping formalization, activation, and reconciliation

**Files:**
- Create: `sci-weave/centre-control/research-map/src/research_mapping/formalization.py`
- Modify: `sci-weave/centre-control/research-map/src/research_mapping/domain.py`
- Modify: `sci-weave/centre-control/research-map/src/research_mapping/terminus_store.py`
- Modify: `sci-weave/centre-control/research-map/src/research_mapping/sqlite_store.py`
- Modify: `sci-weave/centre-control/research-map/src/research_mapping/schema.sql`
- Test: `sci-weave/centre-control/research-map/tests/test_formalization.py`
- Test: `sci-weave/centre-control/research-map/tests/test_terminus_integration.py`
- Update evidence: `.tickets/ai4-1qyc.md` (assignee confirmation required)

- [ ] **Step 1: Add failing tests for eligibility and stable operation identity.** Cover missing/unauthorized Owner approval, unlocked candidate, incomplete evidence, stale base, and operation ID bound to MR, selected solution, locked head, base, and approval event. No formal snapshot may be written when preconditions fail.
- [ ] **Step 2: Run focused tests and verify expected missing-service failures.**

Run: `uv run --locked python -m unittest tests.test_formalization -v`
Expected: the new test cases fail because formalization service is absent.

- [ ] **Step 3: Implement preflight and append-only attempt lifecycle.** Use Mapping statuses `requested`, `in_progress`, `graph_ready`, `reconciliation_required`, `succeeded`, and `failed`. Each attempt gets its own result ID and increasing attempt number; operation identity remains stable for unchanged inputs.
- [ ] **Step 4: Add failing tests for formal snapshot write and exact verification.** Assert explicit failure is `failed`; unknown write/readback is `reconciliation_required`; confirmed exact candidate-derived snapshot transitions only to `graph_ready` and remains invisible to Formal Query.
- [ ] **Step 5: Implement TerminusStore formal snapshot operation and readback.** Return explicit confirmed/failure/unknown outcomes. Confirm exact store, branch, commit, canonical digest, and equivalence with locked candidate before activation.
- [ ] **Step 6: Add failing SQLite activation tests.** Assert a single transaction creates FormalMappingRevision, conditionally updates pointer from expected base, records succeeded result and source disposition; injected transaction failure leaves all governance rows and pointer unchanged. Concurrent base advancement must refuse activation.
- [ ] **Step 7: Implement atomic conditional activation.** Ensure the succeeded result and current pointer become visible together; Formal Query continues to expose old version until commit.
- [ ] **Step 8: Add failing reconciliation and notification tests.** Cover lost activation acknowledgment with already-committed matching rows, old-pointer retry using the same exact commit, partial/mismatched evidence remaining reconciliation-required, and notification failure leaving succeeded revision active.
- [ ] **Step 9: Implement reconciliation and post-activation notification recording.** Reconcile from SQLite and exact TerminusDB readback; never infer success from branch existence or call return alone. Do not perform cross-store rollback.
- [ ] **Step 10: Run all Mapping unit tests and explicit real-store integration tests.**

Run: `uv run --locked python -m unittest discover -s tests -v`
Run: `uv run --locked python -m unittest discover -s tests -p "test_terminus_integration.py" -v`
Expected: unit suite passes; enabled integration suite validates the exact formal Commit. Missing service means report blocked, not passed.

- [ ] **Step 11: Record evidence in `ai4-1qyc`; run `fer dep cycle`.** Do not close before all success, failure, unknown, recovery, and notification criteria are backed by tests.

## Task 4: Complete Wiki formal query qualification coverage

**Files:**
- Modify: `sci-weave/centre-control/research-wiki/tests/test_formal_query_integration.py`
- Modify: `sci-weave/centre-control/research-wiki/tests/test_formal_query.py`
- Modify only if required by failing tests: `sci-weave/centre-control/research-wiki/src/llm_wiki/formal_query.py`
- Update evidence: `.tickets/ai4-91tk.md` (assignee confirmation required)

- [ ] **Step 1: Add failing service-level integration assertions using real ResourceReviewService and exact ResourceVersion.** Cover approved in-scope, pending, withdrawn, and scope-mismatched qualifications while preserving the original reference ID. Use SQLite records and TerminusDB exact Commit fixtures.
- [ ] **Step 2: Run focused query tests and verify missing qualification integration.**

Run: `uv run --locked python -m unittest tests.test_formal_query -v`
Expected: missing end-to-end qualification behavior fails before any production change.

- [ ] **Step 3: Make the minimal query change only if tests prove a contract gap.** Never replace a reference with a newer ResourceVersion; unavailable qualification stays pending/unknown and cannot appear approved.
- [ ] **Step 4: Run Wiki unit suite.**

Run: `uv run --locked python -m unittest discover -s tests -v`
Expected: all unit tests pass.

- [ ] **Step 5: Run formal query and exact ResourceVersion TerminusDB integration suites explicitly.**

Run: `uv run --locked python -m unittest discover -s tests -p "test_formal_query_integration.py" -v`
Run: `uv run --locked python -m unittest discover -s tests -p "test_terminus_integration.py" -v`
Expected: service-level and exact-version tests pass against the configured local service; no skipped integration counted as evidence.

- [ ] **Step 6: Record exact evidence in `ai4-91tk`; preserve ticket open if any acceptance condition is unproven.**

## Task 5: Implement Wiki candidate submission and exact result recovery

**Files:**
- Create: `sci-weave/centre-control/research-wiki/src/llm_wiki/candidate_submission.py`
- Modify: `sci-weave/centre-control/research-wiki/src/llm_wiki/domain.py`
- Modify: `sci-weave/centre-control/research-wiki/src/llm_wiki/terminus_store.py`
- Modify: `sci-weave/centre-control/research-wiki/src/llm_wiki/sqlite_store.py`
- Modify: `sci-weave/centre-control/research-wiki/src/llm_wiki/schema.sql`
- Test: `sci-weave/centre-control/research-wiki/tests/test_candidate_submission.py`
- Test: `sci-weave/centre-control/research-wiki/tests/test_terminus_integration.py`
- Update evidence: `.tickets/ai4-txhf.md` (assignee confirmation required)

- [ ] **Step 1: Add failing tests for atomic document-plus-reference acceptance.** Assert complete structured WikiDocument body and all exact ResourceReference targets are one unit; reject missing, cross-domain, or disallowed Proposal candidate target without partial persistence.
- [ ] **Step 2: Run focused test to verify the candidate service is absent.**

Run: `uv run --locked python -m unittest tests.test_candidate_submission -v`
Expected: new service behavior fails before implementation.

- [ ] **Step 3: Implement candidate input validation and qualification display.** Permit pending/rejected/revoked exact resource targets only in isolated candidate with truthful qualification metadata; mark candidate non-reviewable when any qualification is ineligible. Do not infer newest versions.
- [ ] **Step 4: Add failing tests for idempotency, stale base, exact candidate persistence, and unknown outcome.** Same identity/content must return original IDs; conflicting identity/content must return conflict; unknown storage outcome must not persist an approvable candidate or create duplicate logical records.
- [ ] **Step 5: Implement TerminusDB candidate write and exact identity readback.** Use stable operation marker, exact base Commit, unique isolated candidate branch, canonical snapshot digest and exact Commit. Confirm complete body/reference snapshot before SQLite transaction.
- [ ] **Step 6: Add failing tests for unknown-result reconciliation and resource review gates.** A same-identity retry must locate and verify the exact first candidate; if evidence cannot be proven remain unknown. Candidate may reference a pending resource but cannot be submitted into Project Owner review.
- [ ] **Step 7: Implement idempotent reconciliation and SQLite atomic records.** Write Submission, Proposal, CandidateCommit and AuditEvent together only after exact snapshot confirmation; preserve records and detect key/content mismatch.
- [ ] **Step 8: Run Wiki unit suite.**

Run: `uv run --locked python -m unittest discover -s tests -v`
Expected: all unit tests pass.

- [ ] **Step 9: Run explicit TerminusDB candidate integration tests.** Verify isolated branch, exact base, complete reference snapshot, commit readback, same-identity replay and temporary database cleanup.

Run: `uv run --locked python -m unittest discover -s tests -p "test_terminus_integration.py" -v`
Expected: all enabled tests pass without skips for this evidence.

- [ ] **Step 10: Record `ai4-txhf` evidence and run `fer dep cycle`.**

## Task 6: Implement Wiki review, formalization, and recovery

**Files:**
- Create: `sci-weave/centre-control/research-wiki/src/llm_wiki/review.py`
- Create: `sci-weave/centre-control/research-wiki/src/llm_wiki/formalization.py`
- Modify: `sci-weave/centre-control/research-wiki/src/llm_wiki/formal_domain.py`
- Modify: `sci-weave/centre-control/research-wiki/src/llm_wiki/terminus_store.py`
- Modify: `sci-weave/centre-control/research-wiki/src/llm_wiki/sqlite_store.py`
- Modify: `sci-weave/centre-control/research-wiki/src/llm_wiki/schema.sql`
- Test: `sci-weave/centre-control/research-wiki/tests/test_review.py`
- Test: `sci-weave/centre-control/research-wiki/tests/test_formalization.py`
- Test: `sci-weave/centre-control/research-wiki/tests/test_terminus_integration.py`
- Update evidence: `.tickets/ai4-jdjx.md` (assignee confirmation required)

- [ ] **Step 1: Add failing tests for exact preview, conflict, and review evidence.** Bind previews to candidate head and base FormalWikiRevision; cover document/reference conflicts, stale base/head, complete scheme selection, submission reviewer evidence, and Owner approve/reject decision. Resource qualification, Wiki content review, and Owner publication review remain separately recorded.
- [ ] **Step 2: Run focused review tests and verify expected failure.**

Run: `uv run --locked python -m unittest tests.test_review -v`
Expected: review service missing or behavior failure.

- [ ] **Step 3: Implement Wiki preview, locked Merge Request Buffer, and separate decisions.** Persist evidence and stable references only; keep document/resource body in TerminusDB. Any head/base change invalidates old preview.
- [ ] **Step 4: Add failing tests for formalization eligibility and Wiki-specific states.** Cover Owner approval, current scope-valid ResourceVersion decisions, exact base, stable operation identity, resource decision change after approval, and transitions among `requested`, `in_progress`, `store_ready`, `reconciliation_required`, `succeeded`, and `failed`.
- [ ] **Step 5: Implement preflight and append-only attempts.** Formalization operation binds MR, full selected candidate, locked head, base, Owner event, and exact resource approval IDs. Missing or changed resource decision prevents store write/activation; reapproval requires a new Owner event and operation identity.
- [ ] **Step 6: Add failing tests for exact formal Commit write/readback and SQLite atomic activation.** Assert candidate body/reference snapshot matches exact formal Commit; SQLite activation atomically creates FormalWikiRevision, conditionally changes pointer, records succeeded result with approval IDs and source disposition. Forced transaction failure leaves all rows and pointer unchanged.
- [ ] **Step 7: Implement formal TerminusStore operation and single-transaction activation.** Use Wiki-only store contracts/status names; no Mapping state or schema sharing.
- [ ] **Step 8: Add failing recovery tests.** Cover TerminusDB write unknown, confirmed Commit with SQLite failure, SQLite commit acknowledgment lost, reconciliation finds already active matching revision, old pointer retries same Commit, conflicts/partial evidence remain blocked, notification failure does not roll back.
- [ ] **Step 9: Implement exact-identity reconciliation and notification recording.** Re-read both stores; never activate based solely on a prior write response or branch existence; never create duplicate FormalWikiRevision.
- [ ] **Step 10: Run Wiki unit tests and explicit TerminusDB service integration tests.**

Run: `uv run --locked python -m unittest discover -s tests -v`
Run: `uv run --locked python -m unittest discover -s tests -p "test_terminus_integration.py" -v`
Expected: all unit and enabled integration cases pass. If TerminusDB unavailable, mark real-store evidence blocked and do not claim ticket complete.

- [ ] **Step 11: Record `ai4-jdjx` full evidence and run `fer dep cycle`.**

## Final verification

- [ ] Run `uv sync --locked` in each independent subproject.
- [ ] Run full unit suites from `sci-weave/centre-control/research-map/` and `sci-weave/centre-control/research-wiki/`.
- [ ] Run all required TerminusDB integration tests explicitly; inspect output for skips.
- [ ] Run `fer dep cycle` and `python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py check`.
- [ ] Run `git diff --check`; inspect `git status --short` to confirm no `.env`, caches, virtual environments, generated artifacts, or unrelated changes are staged/modified.
- [ ] Ensure each ticket evidence is written only by its assignee and only after rereading its latest content; leave blocked/open tickets open rather than overstating completion.
