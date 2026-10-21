# Mapping and Wiki Vertical Slices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement independent Python standard-library slices for formal Mapping reads and Wiki ResourceVersion qualification, using SQLite governance records and a fail-closed TerminusDB adapter boundary.

**Architecture:** Create `sci-weave/research-mapping/` and `sci-weave/llm-wiki/` as independent Python packages, each with its own SQLite store, immutable governance records, `TerminusStore` protocol, and tests. Mapping returns formal graph content only when its pointer, successful formalization record, exact commit identity, and content digest agree. Wiki accepts a qualification decision only for an exact version with verifiable owner/authority and appends every decision or denial attempt. Until the TerminusDB 12.0.8 exact-commit read contract is evidenced, the concrete adapter must return an explicit unavailable result rather than guess an HTTP route or fall back to a branch head.

**Tech Stack:** Python >=3.11 standard library (`sqlite3`, `urllib`, `json`, `hashlib`, `unittest`), `uv` per independent project.

---

## File structure

### `sci-weave/research-mapping/`
- `pyproject.toml`, `uv.lock`, `.env.example`, `README.md`: independent package metadata, locked dependency-free environment, configuration sample, reproducible commands.
- `src/main.py`: minimal composition/configuration entry point.
- `src/research_mapping/{__init__.py,config.py,errors.py,canonical.py,domain.py,schema.sql,sqlite_store.py,terminus_store.py,formal_query.py}`: configuration, stable outcomes, canonical hashing, query model, minimal governance schema/persistence, exact-snapshot boundary, and formal query service.
- `tests/test_formal_query.py`: temporary SQLite and fake store tests for success, absent formal view, inconsistent pointer/result, wrong or missing commit, hash mismatch, unknown/unavailable store result, and no content in failures.
- `tests/test_terminus_integration.py`: opt-in live service check that fails clearly if required config is absent; it may only assert exact-commit behavior through a contract that is confirmed for 12.0.8.

### `sci-weave/llm-wiki/`
- `pyproject.toml`, `uv.lock`, `.env.example`, `README.md`: independent package metadata, locked dependency-free environment, configuration sample, reproducible commands.
- `src/main.py`: minimal composition/configuration entry point.
- `src/llm_wiki/{__init__.py,config.py,errors.py,canonical.py,domain.py,schema.sql,sqlite_store.py,terminus_store.py,resource_review.py}`: configuration, stable outcomes, canonical hashing, resource/version/decision models, audit schema/persistence, exact-resource-version boundary, and qualification service.
- `tests/test_resource_review.py`: temporary SQLite plus fake store/authorizer tests for owner, delegated reviewer, denial, pending attempts, exact-version binding, evidence, scopes, revocation/re-approval, and append-only audit.

## Task 1: Confirm the TerminusDB 12.0.8 read contract

- [ ] Locate the 12.0.8 server/client source or versioned official API docs and identify the exact endpoint and inputs for reading a specific commit, plus how the response identifies store/database/branch/commit.
- [ ] Verify how ResourceVersion documents and their owning Resource `owner_id` and snapshot metadata can be read by exact immutable ID.
- [ ] If primary evidence or a running service cannot establish the contract, keep the concrete HTTP method fail-closed (`unavailable`), document the unresolved evidence, and do not invent query parameters, paths, headers, or a successful integration assertion.

## Task 2: Build Mapping formal query with TDD

- [ ] Write the formal-query tests first and run them to confirm the missing package fails for the expected import/API reason.
- [ ] Add the minimal independent package scaffold and dependency-free project metadata; generate its `uv.lock` with `uv lock`.
- [ ] Add the smallest schema/store implementation to persist current pointer, FormalMappingRevision, and succeeded FormalizationResult in foreign-key-enabled SQLite.
- [ ] Add domain result types, canonical JSON SHA-256, and the injected exact-snapshot store protocol.
- [ ] Implement `FormalQueryService.get_current(mapping_domain_id)` so only a matching active pointer + succeeded result + FormalMappingRevision + exact confirmed commit + matching digest returns `available` with graph content.
- [ ] Run the focused test to confirm green, then add one failing test at a time for missing/inconsistent/unavailable cases and implement minimal fail-closed outcomes.
- [ ] Add config, entry point, README commands, and an opt-in integration test that makes no success claim unless the exact contract and local service are available.

## Task 3: Build Wiki resource qualification with TDD

- [ ] Write the resource-review tests first and run them to confirm the missing package fails for the expected import/API reason.
- [ ] Add the minimal independent package scaffold and dependency-free project metadata; generate its `uv.lock` with `uv lock`.
- [ ] Add the smallest foreign-key-enabled SQLite schema/store for append-only resource review and audit records.
- [ ] Add resource/version/review models, canonical hashing, and injected exact-version TerminusStore plus AuthorizationVerifier protocols.
- [ ] Implement `ResourceReviewService.record_decision(...)`: verify exact returned version ID and owner; require direct owner match or affirmative injected authorization verification; on missing/unconfirmed version or authority append a denial attempt and preserve `pending` qualification.
- [ ] Implement `get_current_qualification(...)` using only immutable decisions applicable to requested scope, preserving unknown provenance/license/attribution/snapshot facts and returning explicit limits.
- [ ] Add tests for approve/reject/revoke/re-approve, scopes, unknown evidence, and append-only audit; run focused tests red/green for each behavior.
- [ ] Add config, entry point, README commands, and note the live TerminusDB resource adapter status without asserting unverified HTTP behavior.

## Task 4: Verify both independent projects

- [ ] Run `uv sync --locked` and `uv run --env-file .env python -m unittest discover -s tests -v` separately from each project root, using only examples needed by tests.
- [ ] Run each explicit integration-test command and record whether Docker/TerminusDB was available; a missing local service is a blocker, not a passing integration test.
- [ ] Run `git diff --check` and review all new files plus the original dirty-worktree snapshot; do not reset, overwrite, stage, or revert unrelated pre-existing changes.
- [ ] Re-read both tickets and append implementation/test evidence only after the test results are real; keep ticket status open until every acceptance criterion is met.
