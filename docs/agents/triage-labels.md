# Triage Labels

The engineering triage skill uses two category roles and five workflow roles. For fer, these roles are represented by tags in ticket frontmatter. Keep them separate from fer's `status` field and from the ticket `type` field (`task`, `epic`, `prototype`, and similar work shapes).

| Canonical role | fer tag | Meaning |
| --- | --- | --- |
| `bug` | `bug` | Something is broken |
| `enhancement` | `enhancement` | A feature or improvement request |
| `needs-triage` | `needs-triage` | Maintainer evaluation is needed |
| `needs-info` | `needs-info` | Waiting for reporter information |
| `ready-for-agent` | `ready-for-agent` | Fully specified and ready for an agent |
| `ready-for-human` | `ready-for-human` | Requires human judgment or implementation |
| `wontfix` | `wontfix` | Will not be actioned; close with the required explanation |

Every triaged ticket should have exactly one category tag and one workflow-role tag. `open`, `in_progress`, and `closed` remain the lifecycle statuses managed by fer; they do not replace these triage-role tags.
