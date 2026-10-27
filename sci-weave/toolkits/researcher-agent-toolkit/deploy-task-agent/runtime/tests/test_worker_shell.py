"""Worker shell behaviour (ai4-g1km): draft first, then mark processed."""

from __future__ import annotations

import unittest

from work_agent_runtime.fast_agent_runtime import AgentOutcome
from work_agent_runtime.worker_shell import WorkerRequest, run_queued_once


class _Inbox:
    def __init__(self, rows):
        self.rows = rows
        self.processed: list[str] = []

    def list_status(self, status):
        assert status == "queued"
        return list(self.rows)

    def mark_processed(self, dedupe_key):
        self.processed.append(dedupe_key)


class _Drafts:
    def __init__(self, error=None):
        self.written: list[tuple[str, str]] = []
        self.error = error

    def write(self, *, target_id, payload):
        if self.error is not None:
            raise self.error
        self.written.append((target_id, payload))
        return f"draft-{target_id}"


class _Runtime:
    def __init__(self, rows, drafts=None):
        self.inbox = _Inbox(rows)
        self.drafts = drafts or _Drafts()


class _Agent:
    def __init__(self, outcome):
        self.outcome = outcome
        self.requests: list[WorkerRequest] = []

    def run(self, request):
        self.requests.append(request)
        return self.outcome


def _row(dedupe_key="node-1:event-1", target_id="node-1", agent_definition="researcher"):
    return {
        "dedupe_key": dedupe_key,
        "target_id": target_id,
        "event_id": "event-1",
        "agent_definition": agent_definition,
        "status": "queued",
    }


class RunQueuedOnceTests(unittest.TestCase):
    def test_a_completed_run_writes_the_draft_then_marks_processed(self) -> None:
        runtime = _Runtime([_row()])
        agent = _Agent(AgentOutcome("completed", result_summary="the answer"))

        results = run_queued_once(runtime, agent)

        self.assertEqual(runtime.drafts.written, [("node-1", "the answer")])
        self.assertEqual(runtime.inbox.processed, ["node-1:event-1"])
        self.assertEqual(results[0]["status"], "completed")
        self.assertEqual(results[0]["draft_id"], "draft-node-1")

    def test_the_request_carries_the_command_and_a_stable_session(self) -> None:
        runtime = _Runtime([_row()])
        agent = _Agent(AgentOutcome("completed", result_summary="ok"))

        run_queued_once(runtime, agent)

        request = agent.requests[0]
        self.assertEqual(request.task_node_id, "node-1")
        self.assertEqual(request.command_text, "researcher")
        self.assertEqual(request.session_id, "node-1:event-1")
        self.assertEqual(request.execution_id, "node-1:event-1")

    def test_a_failed_run_leaves_the_row_queued(self) -> None:
        runtime = _Runtime([_row()])
        agent = _Agent(AgentOutcome("failed", error_summary="fast_agent_runtime_error"))

        results = run_queued_once(runtime, agent)

        self.assertEqual(runtime.inbox.processed, [])
        self.assertEqual(runtime.drafts.written, [])
        self.assertEqual(results[0]["error_code"], "fast_agent_runtime_error")

    def test_a_draft_failure_keeps_the_row_replayable(self) -> None:
        runtime = _Runtime([_row()], drafts=_Drafts(error=RuntimeError("buffer down")))
        agent = _Agent(AgentOutcome("completed", result_summary="ok"))

        with self.assertRaises(RuntimeError):
            run_queued_once(runtime, agent)

        self.assertEqual(runtime.inbox.processed, [])

    def test_the_limit_caps_how_many_rows_run(self) -> None:
        runtime = _Runtime([_row(), _row("node-2:event-2", "node-2")])
        agent = _Agent(AgentOutcome("completed", result_summary="ok"))

        results = run_queued_once(runtime, agent, limit=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(runtime.inbox.processed, ["node-1:event-1"])

    def test_no_inbox_means_nothing_to_do(self) -> None:
        class _NoInbox:
            inbox = None
            drafts = _Drafts()

        self.assertEqual(run_queued_once(_NoInbox(), _Agent(AgentOutcome("completed"))), [])


if __name__ == "__main__":
    unittest.main()
