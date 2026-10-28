"""Worker shell behaviour (ai4-g1km): draft first, then mark processed."""

from __future__ import annotations

import unittest

from work_agent_runtime.fast_agent_runtime import AgentOutcome
from work_agent_runtime.worker_shell import (
    NO_TASK_TEXT,
    WorkerRequest,
    run_one_queued,
    run_queued_once,
    task_instruction,
)


class _Inbox:
    def __init__(self, rows):
        self.rows = rows
        self.processed: list[str] = []

    def list_status(self, status):
        assert status == "queued"
        return [row for row in self.rows if row["status"] == status]

    def get(self, dedupe_key):
        return next((row for row in self.rows if row["dedupe_key"] == dedupe_key), None)

    def mark_processed(self, dedupe_key):
        self.processed.append(dedupe_key)
        for row in self.rows:
            if row["dedupe_key"] == dedupe_key:
                row["status"] = "processed"


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


def _row(
    dedupe_key="node-1:event-1",
    target_id="node-1",
    agent_definition="researcher",
    command_text="Summarise the three papers on graph contrastive learning.",
):
    return {
        "dedupe_key": dedupe_key,
        "target_id": target_id,
        "event_id": "event-1",
        "agent_definition": agent_definition,
        "command_text": command_text,
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
        self.assertEqual(request.command_text, "Summarise the three papers on graph contrastive learning.")
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

    def test_a_processed_row_is_not_run_twice(self) -> None:
        """The subscriber commits before the worker runs, so a replay is normal.

        Re-running would write a second draft for one handoff.
        """
        runtime = _Runtime([_row()])
        agent = _Agent(AgentOutcome("completed", result_summary="the answer"))
        run_one_queued(runtime, agent, "node-1:event-1")
        again = run_one_queued(runtime, agent, "node-1:event-1")
        self.assertEqual(len(agent.requests), 1)
        self.assertEqual(again[0]["status"], "already_processed")
        self.assertEqual(len(runtime.drafts.written), 1)

    def test_an_unknown_key_is_reported_not_silently_skipped(self) -> None:
        runtime = _Runtime([_row()])
        results = run_one_queued(runtime, _Agent(AgentOutcome("completed")), "nope")
        self.assertEqual(results[0]["status"], "not_found")

    def test_a_row_awaiting_a_binding_is_not_run(self) -> None:
        row = _row()
        row["status"] = "awaiting_workflow_binding"
        runtime = _Runtime([row])
        agent = _Agent(AgentOutcome("completed"))
        results = run_one_queued(runtime, agent, "node-1:event-1")
        self.assertEqual(agent.requests, [])
        self.assertEqual(results[0]["status"], "awaiting_workflow_binding")


class TaskInstructionTests(unittest.TestCase):
    """ai4-1e9e: a node id must never pass for an instruction.

    The old code wrote `row["agent_definition"] or row["target_id"]`, so a
    handoff with no payload reached the model as `"node-2"`. A model given that
    invents a task from the name, and because a plausible draft comes back
    nobody notices the payload was empty. Saying so is the only honest option.
    """

    def test_the_rows_text_is_used_verbatim(self) -> None:
        self.assertEqual(task_instruction(_row()), "Summarise the three papers on graph contrastive learning.")

    def test_surrounding_whitespace_is_trimmed(self) -> None:
        self.assertEqual(task_instruction(_row(command_text="  do it  ")), "do it")

    def test_an_empty_row_does_not_become_the_node_id(self) -> None:
        instruction = task_instruction(_row(target_id="node-2", command_text=""))
        self.assertNotIn("node-2:", instruction)
        self.assertNotEqual(instruction.strip(), "node-2")
        self.assertIn("node-2", instruction, "the node is still named, as a reference")

    def test_the_empty_case_names_the_defect_and_forbids_guessing(self) -> None:
        instruction = task_instruction(_row(command_text=""))
        self.assertEqual(instruction, NO_TASK_TEXT.format(task_node_id="node-1"))
        self.assertIn("no task instruction", instruction)
        self.assertIn("Do not infer the task", instruction)

    def test_a_whitespace_only_row_is_treated_as_empty(self) -> None:
        self.assertIn("no task instruction", task_instruction(_row(command_text="   \n ")))

    def test_the_agent_receives_the_rows_text_not_the_node(self) -> None:
        """Asserted on what `agent.run` was handed, not on an intermediate."""
        runtime = _Runtime([_row(command_text="Compare RAG and long-context baselines.")])
        agent = _Agent(AgentOutcome("completed", result_summary="ok"))
        run_queued_once(runtime, agent)
        self.assertEqual(agent.requests[0].command_text, "Compare RAG and long-context baselines.")

    def test_the_agent_receives_the_explicit_empty_notice_when_there_is_none(self) -> None:
        runtime = _Runtime([_row(command_text="")])
        agent = _Agent(AgentOutcome("completed", result_summary="ok"))
        run_queued_once(runtime, agent)
        self.assertIn("no task instruction", agent.requests[0].command_text)


if __name__ == "__main__":
    unittest.main()
