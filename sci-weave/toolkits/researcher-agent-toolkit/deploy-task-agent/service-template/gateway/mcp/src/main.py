"""Researcher-side disposition MCP: not implemented yet (ai4-58d0).

The role is described in docs/data-flow/work-agent.md (query_execution,
list_pending, cancel_execution, answer_question, review_execution, health).
Until it exists this entry point fails fast: a launcher that prints "ready"
and then serves nothing is worse than one that refuses to start, because the
operator believes the disposition surface is up.
"""

from __future__ import annotations

from work_agent_runtime import WorkAgentRuntime

runtime = WorkAgentRuntime()


def main() -> int:
    raise SystemExit(
        "gateway/mcp is not implemented yet: the disposition tools listed in "
        "docs/data-flow/work-agent.md have no handler. Do not enable "
        "sciweave-task-agent-mcp.service until this role lands (ai4-58d0)."
    )


if __name__ == "__main__":
    raise SystemExit(main())