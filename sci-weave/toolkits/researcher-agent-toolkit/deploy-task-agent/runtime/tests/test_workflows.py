import unittest

from work_agent_runtime import (
    FakeDraftBox,
    WorkflowExecutor,
    WorkflowRunResult,
    load_config,
)


class RecordingDraftBox(FakeDraftBox):
    def __init__(self):
        self.calls = []

    def write(self, *, target_id, payload):
        self.calls.append((target_id, payload))
        return "draft-1"


AGENTS = {
    "entry": {"identity": "entry", "instruction": "entry", "model": "fake", "allowed_mcp_resources": [], "resources": [], "tools": ["specialist"]},
    "specialist": {"identity": "specialist", "instruction": "specialist", "model": "fake", "allowed_mcp_resources": [], "resources": []},
    "other": {"identity": "other", "instruction": "other", "model": "fake", "allowed_mcp_resources": [], "resources": []},
    "writer": {"identity": "writer", "instruction": "writer", "model": "fake", "allowed_mcp_resources": ["draft"], "resources": []},
}


def config(workflow_type):
    return load_config(
        {"agents": AGENTS, "workflows": {"main": {"type": workflow_type, "entry_agent": "entry", "sub_agents": ["specialist", "other"], "summarizer": "entry", "final_writer": "writer"}}},
        known_mcp_resources={"draft"},
    )


class WorkflowTests(unittest.TestCase):
    def test_each_workflow_has_one_final_draft_and_one_worker_context(self):
        for workflow_type in ("Router", "Orchestrator", "Parallel", "Agents as Tools"):
            with self.subTest(workflow_type=workflow_type):
                calls = []
                drafts = RecordingDraftBox()

                def agent(name, prompt, tools=None):
                    calls.append(name)
                    if name == "entry" and workflow_type == "Router":
                        return "specialist"
                    if name == "writer":
                        return f"final:{prompt}"
                    return f"result:{name}"

                result = WorkflowExecutor(config(workflow_type), agent, drafts).run("main", "question", target_id="task")
                self.assertEqual(result.status, "completed")
                self.assertEqual(result.draft_id, "draft-1")
                self.assertEqual(len(drafts.calls), 1)
                self.assertEqual(result.execution_record_count, 1)
                self.assertEqual(result.worker_lease_count, 1)

    def test_child_failure_is_stable_and_does_not_write_draft(self):
        drafts = RecordingDraftBox()

        def failing_agent(name, prompt, tools=None):
            if name == "specialist":
                raise RuntimeError("model unavailable")
            return "ok"

        result = WorkflowExecutor(config("Parallel"), failing_agent, drafts).run("main", "question", target_id="task")
        self.assertEqual(result, WorkflowRunResult.failed("child_agent_failed", "specialist"))
        self.assertEqual(drafts.calls, [])

    def test_the_final_writer_runs_even_though_no_plan_named_it(self):
        """`final_writer` is the runtime's call, not something the planner picks.

        A model that plans "search, read, done" would otherwise skip the step
        that produces the draft, and the run would end with an answer and no
        draft to review — with nothing in the plan looking wrong.
        """
        for workflow_type in ("Router", "Orchestrator", "Parallel", "Agents as Tools"):
            with self.subTest(workflow_type=workflow_type):
                calls = []

                def agent(name, prompt, tools=None):
                    calls.append(name)
                    if name == "entry" and workflow_type == "Router":
                        return "specialist"
                    return f"{name}-output"

                result = WorkflowExecutor(config(workflow_type), agent, RecordingDraftBox()).run(
                    "main", "question", target_id="task"
                )
                self.assertEqual(result.status, "completed")
                self.assertIn("writer", calls)
                self.assertEqual(calls[-1], "writer", "the writer must be the last model call")

    def test_the_final_writer_reformats_rather_than_passing_the_answer_through(self):
        """The draft payload is a different string from the step's own output.

        The writer is a real model call whose job is to rewrite the answer in
        draft form; a test that only counts calls would still pass if the
        executor passed the previous string straight through.
        """
        drafts = RecordingDraftBox()

        def agent(name, prompt, tools=None):
            if name == "writer":
                # Orchestrator replaces the child results with the summarizer's
                # output, so what the writer sees is the summary, not the raw
                # child answers.
                self.assertIn("entry-output", prompt, "the writer must see the summarised result")
                return "rewritten as a draft"
            return f"{name}-output"

        WorkflowExecutor(config("Orchestrator"), agent, drafts).run(
            "main", "question", target_id="task"
        )
        self.assertEqual(drafts.calls, [("task", "rewritten as a draft")])

    def test_agents_as_tools_exposes_only_declared_child_tools(self):
        seen = []
        drafts = RecordingDraftBox()

        def agent(name, prompt, tools=None):
            if name == "entry":
                seen.append(tuple(sorted(tools)))
                return tools["specialist"]("sub-question")
            if name == "writer":
                return "written"
            return f"answer:{name}"

        result = WorkflowExecutor(config("Agents as Tools"), agent, drafts).run("main", "question", target_id="task")
        self.assertEqual(result.status, "completed")
        self.assertEqual(seen, [("specialist",)])


if __name__ == "__main__":
    unittest.main()
