"""Worker shell: drive one queued inbox row through the agent runtime.

The shell is deliberately thin and lives here rather than in the service
template so it can be tested: it claims one queued handoff, asks the runtime to
run it, writes the answer to the draft box and only then marks the inbox row
processed. A failed run leaves the row ``queued`` so a restart can replay it,
which is the same rule ``WorkAgentRuntime.handle_inbound`` follows.

It runs as a **subprocess the subscriber starts** (ai4-0fwc, ADR-0002). Because
of that it takes the row it was told to run rather than scanning for queued
rows: the subscriber has already claimed that row under the Worker Lease, and a
worker that scanned would race a second subscriber for the same row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AgentRuntime(Protocol):
    def run(self, request: object) -> object: ...


@dataclass(frozen=True)
class WorkerRequest:
    execution_id: str
    task_node_id: str
    session_id: str
    command_text: str


def _result(row: dict, status: str, **extra) -> dict:
    return {"dedupe_key": row["dedupe_key"], "status": status, **extra}


def run_one_queued(runtime, agent: AgentRuntime, dedupe_key: str) -> list[dict]:
    """Run exactly one inbox row, by key.

    Returns a single-element list so callers can print one identical JSON shape
    whether they asked for one row or a batch.

    ``command_text`` still falls back to the task node id when the row carries no
    instruction. That is a placeholder, not a design: the payload that would
    carry the real task text is dropped before the row is written (ai4-1e9e).
    """
    if getattr(runtime, "inbox", None) is None:
        return []
    row = runtime.inbox.get(dedupe_key)
    if row is None:
        return [_result({"dedupe_key": dedupe_key}, "not_found")]
    if row["status"] == "processed":
        # The subscriber committed and the row already ran: re-running would
        # write a second draft for one handoff.
        return [_result(row, "already_processed")]
    if row["status"] != "queued":
        return [_result(row, row["status"])]
    request = WorkerRequest(
        execution_id=row["dedupe_key"],
        task_node_id=row["target_id"],
        session_id=row["dedupe_key"],
        command_text=row["agent_definition"] or row["target_id"],
    )
    outcome = agent.run(request)
    status = getattr(outcome, "status", "failed")
    if status != "completed":
        return [_result(row, status, error_code=getattr(outcome, "error_summary", None))]
    payload = getattr(outcome, "result_summary", None) or ""
    draft_id = runtime.drafts.write(target_id=row["target_id"], payload=payload)
    runtime.inbox.mark_processed(row["dedupe_key"])
    return [_result(row, "completed", draft_id=draft_id)]


def run_queued_once(runtime, agent: AgentRuntime, *, limit: int = 1) -> list[dict]:
    """Run up to ``limit`` queued handoffs and report what happened to each.

    The batch form, kept for the one-shot bring-up run
    (``service-template/worker`` without a key) and for the tests that use it as
    a shortcut. The subscriber uses `run_one_queued`.
    """
    if getattr(runtime, "inbox", None) is None:
        return []
    results: list[dict] = []
    for row in runtime.inbox.list_status("queued")[:limit]:
        results.extend(run_one_queued(runtime, agent, row["dedupe_key"]))
    return results
