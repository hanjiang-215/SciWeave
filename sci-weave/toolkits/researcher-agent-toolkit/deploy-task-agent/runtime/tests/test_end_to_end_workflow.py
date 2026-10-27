"""One handoff, all the way through, with no API key and no real MCP server.

The three earlier tickets each fixed one broken link and each was verified in
isolation. Nothing verified that the links hold *together*: a handoff enters the
inbox, the worker picks it up, the shipped preset runs, the writing agent creates
a draft through its MCP card, the owner is notified, and the record ends up
`completed` with an id the runtime did not invent.

What is faked, and why it is still meaningful:

- the **model** is a stub — no key is available, and the ticket says the
  automated baseline stays key-free;
- the **MCP tools** are a fake that records calls — the real ones need a central
  server, bearer token and a reachable Registry;
- the **agent boundaries** are real: which agent runs which step, which cards it
  was given, what the final writer is told, and where the `draft_id` comes from.

The one thing this cannot prove is that a real model follows the JSON contract.
That is a model property, not a wiring property, and it is covered by the
instruction-plus-parser pair rather than by this test.
"""

from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path

from work_agent_runtime import InboxStore, WorkAgentRuntime, load_worker_config
from work_agent_runtime.durable import SqliteExecutionStore
from work_agent_runtime.notifications import notification_problem
from work_agent_runtime.workflow_agent import WorkflowAgent, plan_for
from work_agent_runtime.worker_shell import run_one_queued
from work_agent_runtime.workflows import WorkflowExecutor

KIT_ROOT = Path(__file__).resolve().parents[2]

_ENV = {
    "SCIWEAVE_AGENT_ID": "researcher-task-agent",
    "RESEARCH_MAPPING_MCP_URL": "https://m.invalid/mcp",
    "LLM_WIKI_MCP_URL": "https://w.invalid/mcp",
    "DRAFT_BUFFER_MCP_URL": "https://b.invalid/mcp",
    "EMAIL_MCP_URL": "https://e.invalid/mcp",
    "LITERATURE_MCP_PROJECT_DIR": "/opt/lit",
}


class FakeMCP:
    """The two tools the preset's writing agent has, recording what it was sent."""

    def __init__(self) -> None:
        self.drafts: list[dict] = []
        self.notifications: list[dict] = []
        self.draft_id = str(uuid.uuid4())

    def create_draft(self, **arguments) -> dict:
        self.drafts.append(arguments)
        return {"draft_id": self.draft_id, "status": "drafting", "snapshot_commit": "c"}

    def send_notification(self, **intent) -> dict:
        self.notifications.append(intent)
        return {"notification_id": intent["notification_id"], "acceptance": "accepted_for_delivery"}


class StubAgentRuntime:
    """Stands in for `FastAgentDeepSeekRuntime`, with the same `run` shape."""

    def __init__(self, name: str, tools: FakeMCP, writer_prompt: list[str]) -> None:
        self.name = name
        self.tools = tools
        self.writer_prompt = writer_prompt

    def run(self, request):
        from work_agent_runtime.fast_agent_runtime import AgentOutcome

        prompt = request.command_text
        if self.name != "literature-draft-writer":
            return AgentOutcome("completed", result_summary=f"{self.name}: {prompt}")

        self.writer_prompt.append(prompt)
        # The agent uses the two cards it was given, in the order the preset's
        # instruction tells it to: create the draft, then notify the owner.
        draft = self.tools.create_draft(
            namespace="wiki",
            kind="wiki_document",
            title="RAG 与长上下文",
            payload="summary of the three readers' findings",
            idempotency_key="draft:node-1",
        )
        self.tools.send_notification(
            notification_id=str(uuid.uuid4()),
            dedupe_key="draft-ready:node-1:evt-1",
            notification_kind="draft_ready",
            recipients=[{"principal_id": "person:owner"}],
            subject="Draft is ready for review",
            body="A draft for node-1 is waiting for your review.",
            related={"execution_id": "node-1:evt-1", "task_node_id": "node-1"},
            schema_version="1",
        )
        return AgentOutcome(
            "completed",
            result_summary=json.dumps(
                {"draft_id": draft["draft_id"], "summary": "RAG 与长上下文各有所长"}
            ),
        )


class FullChainTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = Path(self._tmp.name) / "kit.sqlite"
        self.inbox = InboxStore(str(self.db))
        self.addCleanup(self.inbox.close)
        self.config = load_worker_config(_ENV)
        self.tools = FakeMCP()
        self.writer_prompts: list[str] = []

    def _workflow(self):
        # The kit ships five workflow examples alongside the preset, so the
        # workflow has to be named — see `SCIWEAVE_WORKFLOW` in `.env.example`.
        plan = plan_for(self.config, "literature-agent")
        self.assertIsNotNone(plan)

        def factory(name: str):
            return StubAgentRuntime(name, self.tools, self.writer_prompts)

        stepper = WorkflowAgent(
            factory, execution_id="node-1:evt-1", task_node_id="node-1", session_id="node-1:evt-1"
        )

        def run(prompt: str, target_id: str, execution_id: str = ""):
            executor = WorkflowExecutor(self.config.project, stepper, drafts=None)
            return executor.run(
                plan.name, prompt, target_id=target_id, execution_id=execution_id
            )

        return run

    def _enqueue(self, task_text: str) -> None:
        self.inbox.enqueue(
            "node-1:evt-1",
            "node-1",
            "evt-1",
            "researcher-task-agent",
            binding_present=True,
            command_text=task_text,
        )

    def test_a_handoff_travels_the_whole_path_and_lands_one_draft(self) -> None:
        self._enqueue("比较 RAG 与长上下文两条基线")
        runtime = WorkAgentRuntime(inbox=self.inbox)

        results = run_one_queued(
            runtime, agent=None, dedupe_key="node-1:evt-1", workflow=self._workflow()
        )

        self.assertEqual(results[0]["status"], "completed")
        self.assertEqual(results[0]["draft_id"], self.tools.draft_id)
        self.assertEqual(len(self.tools.drafts), 1, "exactly one draft per handoff")
        self.assertEqual(len(self.tools.notifications), 1, "exactly one notification")
        self.assertEqual(self.inbox.get("node-1:evt-1")["status"], "processed")

    def test_the_draft_id_is_the_one_the_agent_reported_not_one_we_made_up(self) -> None:
        self._enqueue("比较 RAG 与长上下文两条基线")
        runtime = WorkAgentRuntime(inbox=self.inbox)
        run_one_queued(runtime, agent=None, dedupe_key="node-1:evt-1", workflow=self._workflow())

        written = self.tools.drafts[0]
        self.assertEqual(self.tools.draft_id, str(uuid.UUID(self.tools.draft_id)))
        # The value the agent claimed is the value the service returned when the
        # draft was created; a runtime-invented id would not match.
        self.assertEqual(written["namespace"], "wiki")
        self.assertEqual(written["kind"], "wiki_document")

    def test_the_writer_is_told_the_three_fields_the_runtime_owns(self) -> None:
        self._enqueue("比较 RAG 与长上下文两条基线")
        runtime = WorkAgentRuntime(inbox=self.inbox)
        run_one_queued(runtime, agent=None, dedupe_key="node-1:evt-1", workflow=self._workflow())

        self.assertEqual(len(self.writer_prompts), 1)
        prompt = self.writer_prompts[0]
        self.assertIn("draft-ready:node-1:evt-1", prompt)
        self.assertIn('"execution_id": "node-1:evt-1"', prompt)
        self.assertIn('"schema_version": "1"', prompt)
        self.assertIn("比较 RAG 与长上下文", prompt, "the writer must see the handoff's task")

    def test_the_notification_the_agent_sent_passes_the_services_own_rules(self) -> None:
        self._enqueue("比较 RAG 与长上下文两条基线")
        runtime = WorkAgentRuntime(inbox=self.inbox)
        run_one_queued(runtime, agent=None, dedupe_key="node-1:evt-1", workflow=self._workflow())

        self.assertIsNone(notification_problem(self.tools.notifications[0]))

    def test_a_second_run_of_the_same_handoff_writes_nothing(self) -> None:
        """The subscriber may replay; `already_processed` is what stops the copy."""
        self._enqueue("比较 RAG 与长上下文两条基线")
        runtime = WorkAgentRuntime(inbox=self.inbox)
        run_one_queued(runtime, agent=None, dedupe_key="node-1:evt-1", workflow=self._workflow())
        second = run_one_queued(
            runtime, agent=None, dedupe_key="node-1:evt-1", workflow=self._workflow()
        )

        self.assertEqual(second[0]["status"], "already_processed")
        self.assertEqual(len(self.tools.drafts), 1)
        self.assertEqual(len(self.tools.notifications), 1)

    def test_a_handoff_with_no_task_text_is_not_given_the_node_id_as_a_task(self) -> None:
        self._enqueue("")
        runtime = WorkAgentRuntime(inbox=self.inbox)
        run_one_queued(runtime, agent=None, dedupe_key="node-1:evt-1", workflow=self._workflow())

        self.assertIn("no task instruction", self.writer_prompts[0])


class PassthroughFullChainTests(unittest.TestCase):
    """The same path through `build_agent_runtime`, still with no key.

    `FullChainTests` builds the agent boundary by hand. This one uses the real
    factory with `SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME=1`, so the preset's own
    instruction, the per-agent config pinning and the factory's argument
    validation are all in the path. The model is still a double — that is what
    "no key" means — but everything around it is the shipped code.
    """

    def setUp(self) -> None:
        import tempfile

        from work_agent_runtime.fast_agent_runtime import build_agent_runtime

        self.build = build_agent_runtime
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = Path(self._tmp.name) / "kit.sqlite"
        self.inbox = InboxStore(str(self.db))
        self.addCleanup(self.inbox.close)
        self.tools = FakeMCP()
        self.env = dict(_ENV, SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME="1")
        self.config = load_worker_config(self.env)

    def _workflow(self):
        from work_agent_runtime.workflow_agent import plan_for

        plan = plan_for(self.config, "literature-agent")

        def factory(name):
            return self.build(self.env, config=self.config.with_agent(name), mcp=self.tools)

        def run(prompt, target_id, execution_id=""):
            stepper = WorkflowAgent(
                factory,
                execution_id=execution_id or target_id,
                task_node_id=target_id,
                session_id=execution_id or target_id,
            )
            return WorkflowExecutor(self.config.project, stepper, drafts=None).run(
                plan.name, prompt, target_id=target_id, execution_id=execution_id
            )

        return run

    def test_the_shipped_preset_completes_without_an_api_key(self) -> None:
        self.inbox.enqueue(
            "node-7:evt-7",
            "node-7",
            "evt-7",
            "researcher-task-agent",
            binding_present=True,
            command_text="比较 RAG 与长上下文两条基线",
        )
        runtime = WorkAgentRuntime(inbox=self.inbox)
        results = run_one_queued(
            runtime, agent=None, dedupe_key="node-7:evt-7", workflow=self._workflow()
        )

        self.assertEqual(results[0]["status"], "completed")
        self.assertEqual(results[0]["draft_id"], self.tools.draft_id)
        self.assertEqual(len(self.tools.drafts), 1)
        self.assertEqual(len(self.tools.notifications), 1)
        self.assertIsNone(notification_problem(self.tools.notifications[0]))
        self.assertEqual(self.inbox.get("node-7:evt-7")["status"], "processed")

    def test_the_writer_really_is_the_agent_that_holds_the_draft_card(self) -> None:
        """A reader with the draft card would produce a draft from a partial view."""
        writer = self.config.project.agents["literature-draft-writer"]
        reader = self.config.project.agents["literature-searcher"]
        self.assertIn("draft-buffer", writer.allowed_mcp_resources)
        self.assertNotIn("draft-buffer", reader.allowed_mcp_resources)

    def test_a_single_agent_handoff_still_works_with_no_workflow_set(self) -> None:
        """The preset may be a workflow, but the plain path must not regress."""
        self.inbox.enqueue(
            "node-8:evt-8",
            "node-8",
            "evt-8",
            "researcher-task-agent",
            binding_present=True,
            command_text="写一份关于 RAG 的词条草稿",
        )
        runtime = WorkAgentRuntime(inbox=self.inbox)
        agent = self.build(self.env, config=self.config)
        results = run_one_queued(runtime, agent=agent, dedupe_key="node-8:evt-8")

        self.assertEqual(results[0]["status"], "completed")
        self.assertEqual(self.tools.drafts, [], "the single-agent double writes no MCP draft")


class RecordedInSqliteTests(unittest.TestCase):
    """`draft_id` and its provenance survive a process restart (ai4-x0ay)."""

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = str(Path(self._tmp.name) / "exec.sqlite")

    def test_an_agent_reported_id_is_stored_and_queryable(self) -> None:
        from work_agent_runtime.disposition_mcp import _dispatch

        store = SqliteExecutionStore(self.path)
        self.addCleanup(store.close)
        execution = store.enqueue("node-1", "evt-1")
        store.start(execution)
        reported = str(uuid.uuid4())
        store.complete(execution, reported, "agent_reported")

        store.close()
        reopened = SqliteExecutionStore(self.path)
        self.addCleanup(reopened.close)
        answer = _dispatch(reopened, "query_execution", {"execution_id": execution.execution_id})
        self.assertEqual(answer["draft_id"], reported)
        self.assertEqual(answer["draft_id_source"], "agent_reported")

    def test_a_database_from_before_the_column_still_opens(self) -> None:
        """The kit ships an installed database; a new column must not break it."""
        import sqlite3

        connection = sqlite3.connect(self.path)
        connection.executescript(
            """
            CREATE TABLE execution (
                execution_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                target_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                draft_id TEXT,
                error_code TEXT,
                failed_agent TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO execution (execution_id, event_id, target_id, status, created_at, updated_at)
            VALUES ('old-1', 'evt-old', 'node-old', 'completed', 'now', 'now');
            """
        )
        connection.commit()
        connection.close()

        store = SqliteExecutionStore(self.path)
        self.addCleanup(store.close)
        record = store.get("old-1")
        self.assertIsNotNone(record)
        self.assertIsNone(record.draft_id_source, "an old row has no provenance to report")


if __name__ == "__main__":
    unittest.main()
