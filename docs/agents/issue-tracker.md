# Issue Tracker

## Tracker

`fer` is the sole issue tracker for this repository. Tickets are stored as individual Markdown files in `.tickets/`; `fer create` supplies the canonical `ai4-<id>.md` filename, and the frontmatter `id` and `created` fields are authoritative.

## Workflow

- Use the `fer` CLI to create, inspect, start, update status, close, add notes, and manage dependencies or links.
- The lifecycle statuses are `open`, `in_progress`, and `closed`. Close a ticket only after its acceptance criteria are verified; leave unresolved or blocked work active and record the next step.
- Use `fer dep` / `fer undep` for blocking dependencies and `fer link` / `fer unlink` for symmetric relationships.
- Triage comments or notes must begin with the disclaimer required by `.cursor/skills/engineering/triage/SKILL.md`.

Gitee pull requests are managed separately with the `gitee` CLI and are not included as external requests in fer triage.
