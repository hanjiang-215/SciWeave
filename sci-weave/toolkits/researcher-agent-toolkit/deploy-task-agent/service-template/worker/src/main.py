"""Worker entry shell: runs one queued handoff, then exits (ai4-58d0).

The durable queue-driven path lives in ``gateway/subscriber``; this shell is
for one-shot runs during bring-up. It refuses to start while the fast-agent
invocation is still a placeholder, instead of printing "ready" and exiting
successfully with nothing done.
"""

from __future__ import annotations

from work_agent_runtime import WorkAgentRuntime

runtime = WorkAgentRuntime()


def main() -> int:
    raise SystemExit(
        "worker template is not implemented yet: the fast-agent invocation is "
        "still a placeholder (see run_one.py). Use gateway/subscriber for the "
        "durable path until this role lands (ai4-58d0)."
    )


if __name__ == "__main__":
    raise SystemExit(main())