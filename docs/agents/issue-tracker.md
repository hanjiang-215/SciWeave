# Issue Tracker

## Tracker

`fer` is the sole issue tracker for this repository. Tickets are stored as individual Markdown files in `.tickets/`; `fer create` supplies the canonical `ai4-<id>.md` filename, and the frontmatter `id` and `created` fields are authoritative.

## Workflow

- Use the `fer` CLI to create, inspect, start, update status, close, add notes, and manage dependencies or links.
- Set `assignee` explicitly with `fer create -a <handle>`; do not rely on the default from `git config user.name`, which may be a display name rather than the developer's ticket handle. Never use a team name or placeholder.
- The lifecycle statuses are `open`, `in_progress`, and `closed`. Close a ticket only after its acceptance criteria are verified; leave unresolved or blocked work active and record the next step.
- Use `fer dep` / `fer undep` for blocking dependencies and `fer link` / `fer unlink` for symmetric relationships.
- Triage comments or notes must begin with the disclaimer required by `.cursor/skills/engineering/triage/SKILL.md`.

Gitee pull requests are managed separately with the `gitee` CLI and are not included as external requests in fer triage.

## Index

`docs/tickets/INDEX.md` is the generated overview of all tickets. It groups tickets by domain module, gives each a one-line summary, and lists the current frontier, blocked work, ownerless tickets, and cross-module relations. Read it to locate a ticket before opening the full `.tickets/<id>.md` file.

Per-ticket ownership and summaries live in `docs/tickets/meta/<id>.toml`; the module registry lives in `docs/tickets/modules.toml`; status, dependencies, hierarchy, and counts are derived from ticket frontmatter. `.cursor/hooks/ticket-index-sync.py` renders the index automatically after `fer` changes and after edits to `.tickets/*.md`, `meta/*.toml`, or `modules.toml`. New tickets still need a `meta/<id>.toml` file. Review only the changed hunks and verify:

```bash
python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py diff
python .cursor/skills/engineering/ticket-index/scripts/ticket_index.py check
```

`check` exits non-zero when a ticket is missing a `meta` entry or has an empty summary, when a ticket references an unknown module, when a parent/dependency/link reference is broken, or when a generated file is stale. Do not hand-edit `INDEX.md` or `modules/*.md`.
