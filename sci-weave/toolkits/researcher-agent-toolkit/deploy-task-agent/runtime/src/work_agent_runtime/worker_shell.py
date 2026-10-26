"""Worker shell: drive queued inbox rows through the agent runtime (ai4-g1km).

The shell is deliberately thin and lives here rather than in the service
template so it can be tested: it claims one queued handoff at a time, asks the
runtime to run it, writes the answer to the draft box and only then marks the
inbox row processed. A failed run leaves the row ``queued`` so a restart can
replay it, which is the same rule ``WorkAgentRuntime.handle_inbound`` follows.
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


def run_queued_once(runtime, agent: AgentRuntime, *, limit: int = 1) -> list[dict]:
    """Run up to ``limit`` queued handoffs and report what happened to each.

    ``runtime`` is a ``WorkAgentRuntime``: it supplies the inbox and the draft
    box. Nothing is marked processed unless the draft was written.
    """
    if getattr(runtime, "inbox", None) is None:
        return []
    results: list[dict] = []
    for row in runtime.inbox.list_status("queued")[:limit]:
        request = WorkerRequest(
            execution_id=row["dedupe_key"],
            task_node_id=row["target_id"],
            session_id=row["dedupe_key"],
            command_text=row["agent_definition"] or row["target_id"],
        )
        outcome = agent.run(request)
        status = getattr(outcome, "status", "failed")
        if status != "completed":
            results.append(
                {
                    "dedupe_key": row["dedupe_key"],
                    "status": status,
                    "error_code": getattr(outcome, "error_summary", None),
                }
            )
            continue
        payload = getattr(outcome, "result_summary", None) or ""
        draft_id = runtime.drafts.write(target_id=row["target_id"], payload=payload)
        runtime.inbox.mark_processed(row["dedupe_key"])
        results.append(
            {
                "dedupe_key": row["dedupe_key"],
                "status": "completed",
                "draft_id": draft_id,
            }
        )
    return results
