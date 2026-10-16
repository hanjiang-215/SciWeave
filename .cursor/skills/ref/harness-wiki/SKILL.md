---
name: harness-wiki
description: Maintain an LLM Wiki: a long-lived markdown knowledge vault for durable research, design rationale, decisions, and cross-project context. Use when the user wants to initialize, ingest into, query, lint, or maintain a Harness Wiki / LLM Wiki vault.
---

# Harness Wiki Skill

Use this skill to create and maintain an LLM Wiki: a persistent, Obsidian-compatible markdown knowledge vault. The user curates sources and asks questions; you maintain the wiki by summarizing, cross-referencing, filing, surfacing contradictions, and keeping the index and log current.

Harness Wiki is skill-first. MCP is an optional accelerator: if the `harness-wiki` MCP server is available, use its tools for deterministic scaffold/status operations. If MCP is not available, follow this skill manually.

## First response

When the user asks to use Harness Wiki, initialize a vault, ingest a source, query a vault, lint a vault, or maintain durable knowledge:

1. Inspect the current directory for `CLAUDE.md`, `AGENTS.md`, `wiki/index.md`, `wiki/log.md`, and the marker `<!-- harness-wiki:vault-schema -->`.
2. If the vault exists, follow the local schema in `CLAUDE.md` / `AGENTS.md` as the source of truth.
3. If the vault does not exist, ask for only missing product intent that cannot be discovered locally: vault name, domain, and paired projects.
4. If the MCP server is available, call `vault_init` or `vault_status` instead of hand-writing scaffold files. Always pass the target workspace absolute path as `cwd`.
5. If MCP is not available, create or update the scaffold manually according to this skill.

## Optional MCP accelerator

Use MCP when the harness exposes the `harness-wiki` server:

- `vault_init`: create `raw/`, `raw/assets/`, `wiki/entities/`, `wiki/concepts/`, `wiki/sources/`, `wiki/syntheses/`, `CLAUDE.md`, `AGENTS.md`, `wiki/index.md`, and `wiki/log.md`. Pass `cwd` as the target workspace absolute path, `vaultName`, optional `domain`, optional `pairedProjects`, and `force` only for repair.
- `vault_status`: report scaffold state and list `raw/` files that do not have matching `wiki/sources/<slug>.md` pages. Pass `cwd` as the target workspace absolute path.
- `wiki_init_prompt`: fetch the long-form bootstrap/operations prompt when more detailed setup guidance is needed.
- `vault_doctor`: deterministic structural health check — pages missing frontmatter, dead `[[wikilinks]]`, orphan pages, pages absent from `wiki/index.md`, stale source pages (raw file changed since ingest), and broken paired-project paths. Run it as the mechanical first pass of a `lint`, then reason about contradictions and stale claims yourself.
- `vault_search`: plain-text search across `wiki/` pages. Use it to locate relevant pages before answering a query once the vault is too large to scan from `wiki/index.md` alone.
- `vault_stamp`: record `source_file` + `source_sha256` into source-page frontmatter. Run after each ingest so staleness can be detected later; re-run to acknowledge a legitimate re-review.
- `vault_link`: register a sibling project in the Paired-projects table and write a back-pointer into its `CLAUDE.md`. The wiki↔repo wedge.

Do not require MCP for normal ingest, query, or lint work. Those operations are agent-maintained using the vault schema. `vault_doctor` and `vault_search` are accelerators only — when MCP is unavailable, perform the same checks by reading pages and grepping the `wiki/` directory.

If an MCP init appears to create files in the wrong place, inspect the intended workspace path and re-run `vault_init` with `cwd` set to that absolute path.

## Manual initialization

If MCP is unavailable, initialize the vault manually:

1. Create directories:
   - `raw/`
   - `raw/assets/`
   - `wiki/entities/`
   - `wiki/concepts/`
   - `wiki/sources/`
   - `wiki/syntheses/`
2. Write or append a marker-fenced vault schema to `CLAUDE.md`:
   - Start marker: `<!-- harness-wiki:vault-schema -->`
   - End marker: `<!-- /harness-wiki:vault-schema -->`
   - Preserve existing project instructions outside the marker.
3. Write or append `AGENTS.md` as a pointer to `CLAUDE.md`, also marker-fenced if the file already has unrelated content.
4. Create `wiki/index.md` as an empty catalog grouped by entities, concepts, sources, and syntheses.
5. Create `wiki/log.md` with `## [YYYY-MM-DD] schema | Vault initialized`.

The schema must define the three operations below and include a `Paired projects` table, even when it is empty.

## Ingest

Trigger: `ingest raw/<file>` or `ingest <url>`.

1. Read the source end-to-end. Treat `raw/` as immutable.
   - **For a URL:** first save the fetched content into `raw/` (e.g. `raw/<slug>.md`, images into `raw/assets/`) so the source is captured immutably, then ingest that file. Never ingest a URL without persisting it to `raw/` — the wiki must remain traceable to durable local sources.
2. Before writing, summarize key takeaways, contradictions, important entities/concepts, likely pages to touch, and open questions.
3. After confirmation, write `wiki/sources/<slug>.md` with frontmatter, metadata, 3-10 key takeaways, notable quotes, and open questions. Derive `<slug>` from the raw filename in kebab-case (`PRD Checkout V2.pdf` → `prd-checkout-v2.md`) so deterministic tooling can pair the source page with its raw file.
4. Create or update relevant pages in `wiki/entities/`, `wiki/concepts/`, and `wiki/syntheses/`.
5. Add citations with `[[sources/<slug>]]` for non-obvious claims.
6. Update `wiki/index.md`.
7. Append `## [YYYY-MM-DD] ingest | <title>` to `wiki/log.md`.
8. Run `vault_stamp` (or write `source_file` + `source_sha256` into the source page frontmatter) so the raw file's hash is recorded for staleness detection.
9. Report the pages touched.

## Query

Trigger: any user question about the vault's knowledge.

1. Read `wiki/index.md` first.
2. Drill into relevant pages and follow `[[wikilinks]]`.
3. Answer with citations to wiki pages and source summaries.
4. If the answer is a durable comparison, decision, analysis, or reusable explanation, offer to file it in `wiki/syntheses/<slug>.md`.
5. Log non-trivial queries in `wiki/log.md`.

## Lint

Trigger: `lint`, `audit`, `health check`, or equivalent.

Start with the mechanical pass: run `vault_doctor` (or, without MCP, grep the `wiki/` directory) to catch missing frontmatter, dead `[[wikilinks]]`, orphan pages, and pages absent from the index. Then add the judgment-based findings below.

Report:

- Contradictions between pages.
- Stale claims superseded by newer sources.
- Orphan pages with no inbound links.
- Important concepts mentioned without pages.
- Missing cross-references.
- Gaps where new sources or web research would help.
- Suggested next questions.

Append `## [YYYY-MM-DD] lint | <title>` to `wiki/log.md` when the lint is substantive.

## Page conventions

- Filenames are kebab-case.
- Use `[[wikilinks]]` for entities, concepts, sources, and syntheses.
- Every wiki page starts with YAML frontmatter:

```yaml
---
type: entity | concept | source | synthesis
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [source-slug-1, source-slug-2]
tags: [tag1, tag2]
---
```

- Every non-obvious claim should cite a source page.
- Contradictions get an explicit `## Contradictions` section.
- Wiki pages are reference material: lead with the conclusion, prefer bullets/tables, and keep pages easy to re-read.

## Paired projects

Use the vault for durable rationale and design memory. Use sibling project repos for implementation and public deliverables.

The schema must include:

```markdown
## Paired projects
| Project | Path | Purpose | Status |
|---|---|---|---|
| <project-name> | `../<project-name>/` | <one line> | <design / building / shipped> |
```

Register a project with `vault_link` (name, path, purpose, status): it maintains the table and writes a marker-fenced back-pointer into the project's `CLAUDE.md`, so the link is discoverable from both sides.

**The handoff — synthesis → spec → implementation.** When a `wiki/syntheses/*` design is approved, hand it off: create or update the spec in the paired repo and implement there, not in the vault. For a long-running implementation session, use Harness Bridge in that repo to track the current work. When work in a paired project creates durable design decisions or learnings, reflect them back into the vault before finishing.
