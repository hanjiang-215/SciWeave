"""Worker entry shell: run queued handoffs once, then exit.

The durable queue-driven path lives in ``gateway/subscriber``; this shell is for
one-shot runs during bring-up. It builds the real fast-agent runtime from the
environment and drives the queued inbox rows through it, writing each answer to
the draft box. A missing key fails at startup instead of producing a fake
completion, and the passthrough runtime is only reachable through
``SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME=1`` (ai4-g1km).

Startup loads the researcher's configuration (ai4-z3yq). `build_agent_runtime`
reads ``AGENT_DEFINITIONS_PATH`` / ``AGENT_LIBS_PATH`` / ``MCP_LIBS_PATH`` /
``WORKFLOW_LIBS_PATH`` and refuses to start when one is missing or invalid, so
a mistyped path is a startup error rather than a silently ignored edit.
"""

from __future__ import annotations

import json
import logging
import os

from work_agent_runtime import (
    BufferMCPDraftWriter,
    InboxStore,
    WorkerConfigError,
    WorkAgentRuntime,
    build_agent_runtime,
)
from work_agent_runtime.worker_shell import run_queued_once


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value or not value.strip():
        raise SystemExit(f"{name} must be configured through the environment")
    return value.strip()


def build_runtime() -> WorkAgentRuntime:
    runtime = WorkAgentRuntime()
    runtime.inbox = InboxStore(required("DATABASE_PATH"))
    draft_url = os.environ.get("DRAFT_BUFFER_MCP_URL", "").strip()
    draft_token = os.environ.get("DRAFT_BUFFER_MCP_TOKEN", "").strip()
    if draft_url and draft_token:
        runtime.drafts = BufferMCPDraftWriter(
            endpoint=draft_url,
            token=draft_token,
            namespace=os.environ.get("SCIWEAVE_DRAFT_NAMESPACE", "mapping").strip() or "mapping",
            submitter_id=os.environ.get("SCIWEAVE_AGENT_ID", "").strip() or "researcher-task-agent",
        )
    return runtime


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    runtime = build_runtime()
    try:
        agent = build_agent_runtime()
    except ValueError as error:
        raise SystemExit(f"worker runtime is not configured: {error}") from error
    except WorkerConfigError as error:
        # Distinct exit path: a bad configuration is a deployment mistake the
        # researcher has to fix, not a missing credential.
        raise SystemExit(f"worker configuration is invalid: {error}") from error
    config = getattr(agent, "config", None)
    print(
        json.dumps(
            {
                # The passthrough runtime has no config; say so rather than
                # printing `null` and leaving the reader guessing.
                "agent": getattr(config, "agent_name", None) or type(agent).__name__,
                "instruction_source": (getattr(config, "sources", {}) or {}).get(
                    "AGENT_DEFINITIONS_PATH"
                ),
                "workflows": sorted(getattr(getattr(config, "project", None), "workflows", {})),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    limit = int(os.environ.get("SCIWEAVE_WORKER_BATCH", "1"))
    results = run_queued_once(runtime, agent, limit=limit)
    print(json.dumps({"ran": len(results), "results": results}, ensure_ascii=False))
    return 0 if all(item["status"] == "completed" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
