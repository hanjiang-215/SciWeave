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
import sys

from work_agent_runtime import (
    BufferMCPDraftWriter,
    InboxStore,
    WorkerConfigError,
    WorkAgentRuntime,
    build_agent_runtime,
)
from work_agent_runtime.worker_shell import run_one_queued, run_queued_once


def argument(name: str) -> str:
    """Read ``--name value`` or ``--name=value`` from argv, or "".

    argparse would bring a `--help` that prints usage for a process whose real
    interface is its exit code and its JSON stdout; two shapes is enough.
    """
    argv = sys.argv[1:]
    for index, item in enumerate(argv):
        if item == name and index + 1 < len(argv):
            return argv[index + 1].strip()
        if item.startswith(f"{name}="):
            return item.split("=", 1)[1].strip()
    return ""


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
    # One handoff by key when the subscriber started us (ai4-0fwc); a batch scan
    # only for the standalone bring-up run.
    dedupe_key = argument("--dedupe-key")
    if dedupe_key:
        results = run_one_queued(runtime, agent, dedupe_key)
    else:
        results = run_queued_once(runtime, agent, limit=int(os.environ.get("SCIWEAVE_WORKER_BATCH", "1")))
    print(json.dumps({"ran": len(results), "results": results}, ensure_ascii=False))
    # `not_found` and `already_processed` are not failures: the subscriber
    # commits before it dispatches, so a replay that finds a finished row, or a
    # row another worker took, is a normal race. Only a run that should have
    # happened and did not is worth a non-zero exit.
    benign = {"completed", "not_found", "already_processed"}
    return 0 if all(item["status"] in benign for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
