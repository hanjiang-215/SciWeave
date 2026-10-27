"""The worker runs the configured workflow, not just one agent (ai4-x0ay).

`WorkflowExecutor` existed and was tested, and nothing in production called it
— the same shape of defect as ai4-0fwc: a working component with no caller.
These tests pin the wiring: which workflow is chosen, that every step gets its
own agent definition, and that a workflow's draft is written once by the
executor rather than again by the shell.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from work_agent_runtime import FakeDraftBox, load_worker_config
from work_agent_runtime.config import load_config
from work_agent_runtime.workflow_agent import AgentRunFailure, WorkflowAgent, plan_for
from work_agent_runtime.worker_shell import run_one_queued

KIT_ROOT = Path(__file__).resolve().parents[2]

_ENV = {
    "SCIWEAVE_AGENT_ID": "researcher-task-agent",
    "RESEARCH_MAPPING_MCP_URL": "https://m.invalid/mcp",
    "LLM_WIKI_MCP_URL": "https://w.invalid/mcp",
    "DRAFT_BUFFER_MCP_URL": "https://b.invalid/mcp",
    "LITERATURE_MCP_PROJECT_DIR": "/opt/lit",
    "EMAIL_MCP_URL": "https://e.invalid/mcp",
}


class _Outcome:
    def __init__(self, status: str, summary: str = "") -> None:
        self.status = status
        self.result_summary = summary
        self.error_summary = None if status == "completed" else "child_failed"


class _Runtime:
    def __init__(self, summary: str = "answer", status: str = "completed") -> None:
        self.summary = summary
        self.status = status
        self.requests: list[object] = []

    def run(self, request):
        self.requests.append(request)
        return _Outcome(self.status, self.summary)


class WorkflowAgentTests(unittest.TestCase):
    def _agent(self, factory) -> WorkflowAgent:
        return WorkflowAgent(factory, execution_id="exec-1", task_node_id="node-1", session_id="s-1")

    def test_each_step_builds_its_own_runtime_for_that_agent(self) -> None:
        built: list[str] = []
        runtime = _Runtime("evidence")

        def factory(name):
            built.append(name)
            return runtime

        result = self._agent(factory)("literature-searcher", "find papers")
        self.assertEqual(built, ["literature-searcher"])
        self.assertEqual(result, "evidence")

    def test_each_step_gets_a_distinct_session(self) -> None:
        """Sharing one session would let two readers see each other's turns."""
        runtime = _Runtime()
        agent = self._agent(lambda _name: runtime)
        agent("literature-searcher", "a")
        agent("literature-wiki-reader", "b")
        sessions = [request.session_id for request in runtime.requests]
        self.assertEqual(len(set(sessions)), 2)
        self.assertTrue(all("s-1" in session for session in sessions))

    def test_a_failed_step_raises_with_the_agent_named(self) -> None:
        agent = self._agent(lambda _name: _Runtime(status="failed"))
        with self.assertRaises(AgentRunFailure) as caught:
            agent("literature-searcher", "find papers")
        self.assertEqual(caught.exception.agent, "literature-searcher")

    def test_agents_as_tools_is_refused_rather_than_faked(self) -> None:
        """fast-agent cannot call a Python callable as a tool, so say so."""
        agent = self._agent(lambda _name: _Runtime())
        with self.assertRaises(AgentRunFailure) as caught:
            agent("literature-agent", "plan", tools={"x": lambda prompt: prompt})
        self.assertEqual(caught.exception.code, "agents_as_tools_unsupported")


class PlanSelectionTests(unittest.TestCase):
    def _config(self, workflows: dict) -> object:
        agents = {
            name: {
                "identity": name,
                "instruction": name,
                "model": "fake",
                "allowed_mcp_resources": [],
                "resources": [],
            }
            for name in ("entry", "reader", "writer")
        }
        return type(
            "Config",
            (),
            {"project": load_config({"agents": agents, "workflows": workflows})},
        )()

    def _workflow(self, name: str) -> dict:
        return {
            "type": "Orchestrator",
            "entry_agent": "entry",
            "sub_agents": ["reader"],
            "summarizer": "entry",
            "final_writer": "writer",
        }

    def test_a_single_workflow_runs_without_a_selection_variable(self) -> None:
        """The shipped preset declares one workflow; requiring a setting defeats it."""
        plan = plan_for(self._config({"only": self._workflow("only")}), None)
        self.assertEqual(plan.name, "only")

    def test_several_workflows_and_no_selection_stays_single_agent(self) -> None:
        """Guessing which of five examples to run is not a runtime decision."""
        config = self._config({"a": self._workflow("a"), "b": self._workflow("b")})
        self.assertIsNone(plan_for(config, None))

    def test_the_selection_variable_picks_one(self) -> None:
        config = self._config({"a": self._workflow("a"), "b": self._workflow("b")})
        self.assertEqual(plan_for(config, "b").name, "b")

    def test_an_unknown_selection_is_an_error_naming_the_known_ones(self) -> None:
        config = self._config({"a": self._workflow("a")})
        with self.assertRaises(AgentRunFailure) as caught:
            plan_for(config, "nope")
        self.assertIn("a", str(caught.exception))

    def test_a_config_with_no_workflows_stays_single_agent(self) -> None:
        self.assertIsNone(plan_for(self._config({}), None))

    def test_the_plan_names_every_agent_the_workflow_reaches(self) -> None:
        plan = plan_for(self._config({"only": self._workflow("only")}), None)
        self.assertEqual(set(plan.agent_names), {"entry", "reader", "writer"})


class DraftWriterOwnershipTests(unittest.TestCase):
    """Who writes the draft, and what `draft_id` is worth (ai4-x0ay).

    Two paths, decided by the agent's own cards:

    - final writer **without** `draft-buffer`: this process writes the draft and
      reads the id back, so the id is verified by construction;
    - final writer **with** `draft-buffer`: the agent writes it through MCP and
      reports the id in its answer. That id is an unverified claim, which is why
      it is stored with `agent_reported` and returned by `query_execution`.
    """

    def _config(self, writer_servers: list[str]) -> object:
        return load_config(
            known_mcp_resources={"draft-buffer"},
            source={
                "agents": {
                    "entry": {
                        "identity": "e",
                        "instruction": "e",
                        "model": "fake",
                        "allowed_mcp_resources": [],
                        "resources": [],
                    },
                    "writer": {
                        "identity": "w",
                        "instruction": "w",
                        "model": "fake",
                        "allowed_mcp_resources": writer_servers,
                        "resources": [],
                    },
                },
                "workflows": {
                    "main": {
                        "type": "Orchestrator",
                        "entry_agent": "entry",
                        "sub_agents": ["entry"],
                        "summarizer": "entry",
                        "final_writer": "writer",
                    }
                },
            }
        )

    def _run(self, writer_servers, writer_answer: str):
        from work_agent_runtime.workflows import WorkflowExecutor

        class _Drafts:
            def __init__(self):
                self.written: list[str] = []

            def write(self, *, target_id, payload):
                self.written.append(payload)
                return "draft-from-runtime"

        drafts = _Drafts()
        config = self._config(writer_servers)

        def agent(name, prompt, tools=None):
            return writer_answer if name == "writer" else "intermediate"

        result = WorkflowExecutor(config, agent, drafts).run(
            "main", "do it", target_id="node-1"
        )
        return result, drafts

    def test_a_writer_without_the_card_gets_its_draft_written_here(self) -> None:
        result, drafts = self._run([], "the text")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.draft_id, "draft-from-runtime")
        self.assertEqual(result.draft_id_source, "runtime")
        self.assertEqual(drafts.written, ["the text"])

    def test_a_writer_with_the_card_writes_its_own_and_reports_the_id(self) -> None:
        identifier = "3f12df3e-1111-4222-8333-444455556666"
        result, drafts = self._run(
            ["draft-buffer"], '{"draft_id": "%s", "summary": "done"}' % identifier
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.draft_id, identifier)
        self.assertEqual(result.draft_id_source, "agent_reported")
        self.assertEqual(drafts.written, [], "a second draft must not be written")

    def test_a_free_form_answer_without_json_fails_with_a_stable_code(self) -> None:
        """A plausible paragraph is not a draft id; inventing one hides that."""
        result, drafts = self._run(["draft-buffer"], "I wrote the draft, it went well.")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "draft_id_missing")
        self.assertIsNone(result.draft_id)
        self.assertEqual(drafts.written, [])

    def test_a_non_uuid_identifier_is_refused(self) -> None:
        result, _ = self._run(["draft-buffer"], '{"draft_id": "draft-123", "summary": "x"}')
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "draft_id_missing")

    def test_a_json_object_without_a_draft_id_is_refused(self) -> None:
        result, _ = self._run(["draft-buffer"], '{"summary": "no id here"}')
        self.assertEqual(result.status, "failed")

    def test_a_fenced_json_object_is_accepted(self) -> None:
        """Models fence their JSON whatever the instruction says.

        Rejecting a correct answer over punctuation sends the researcher looking
        for a runtime bug instead of reading the draft.
        """
        identifier = "3f12df3e-1111-4222-8333-444455556666"
        fenced = "```json\n{\"draft_id\": \"%s\", \"summary\": \"ok\"}\n```" % identifier
        result, _ = self._run(["draft-buffer"], fenced)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.draft_id, identifier)


class DraftIdParsingTests(unittest.TestCase):
    def test_a_canonical_uuid_is_returned(self) -> None:
        from work_agent_runtime.workflows import reported_draft_id

        identifier = "3f12df3e-1111-4222-8333-444455556666"
        self.assertEqual(
            reported_draft_id('{"draft_id": "%s"}' % identifier), identifier
        )

    def test_uppercase_is_normalised(self) -> None:
        from work_agent_runtime.workflows import reported_draft_id

        upper = "3F12DF3E-1111-4222-8333-444455556666"
        self.assertEqual(
            reported_draft_id('{"draft_id": "%s"}' % upper), upper.lower()
        )

    def test_prose_is_not_parsed(self) -> None:
        from work_agent_runtime.workflows import reported_draft_id

        self.assertIsNone(reported_draft_id("the draft is done"))
        self.assertIsNone(reported_draft_id("{\"draft_id\": 42}"))
        self.assertIsNone(reported_draft_id(""))


class ShippedPresetTests(unittest.TestCase):
    """The preset in `libs/workflow-libs/literature-agent.yaml`, not a fixture."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_worker_config(_ENV)

    def test_the_preset_loads_with_the_four_sub_agents(self) -> None:
        workflow = self.config.project.workflows["literature-agent"]
        self.assertEqual(workflow.workflow_type, "Orchestrator")
        self.assertEqual(
            set(workflow.sub_agents),
            {"literature-searcher", "literature-mapping-reader", "literature-wiki-reader"},
        )
        self.assertEqual(workflow.final_writer, "literature-draft-writer")

    def test_the_planner_settings_survive_the_load(self) -> None:
        """These were written in the ticket's YAML and silently dropped before."""
        workflow = self.config.project.workflows["literature-agent"]
        self.assertEqual(workflow.plan_type, "iterative")
        self.assertEqual(workflow.plan_iterations, 2)

    def test_each_preset_agent_gets_exactly_the_cards_the_design_names(self) -> None:
        agents = self.config.project.agents
        self.assertEqual(agents["literature-searcher"].allowed_mcp_resources, ("literature-search",))
        self.assertEqual(agents["literature-mapping-reader"].allowed_mcp_resources, ("research-mapping",))
        self.assertEqual(agents["literature-wiki-reader"].allowed_mcp_resources, ("research-wiki",))
        self.assertEqual(
            set(agents["literature-draft-writer"].allowed_mcp_resources),
            {"draft-buffer", "email-service"},
        )
        self.assertEqual(
            agents["literature-agent"].allowed_mcp_resources,
            (),
            "fast-agent's orchestrator cannot connect to servers; declaring any is a lie",
        )

    def test_every_preset_agent_has_an_instruction_that_says_what_it_must_not_do(self) -> None:
        for name in (
            "literature-searcher",
            "literature-mapping-reader",
            "literature-wiki-reader",
        ):
            with self.subTest(agent=name):
                self.assertIn("不要写草稿", self.config.project.agents[name].instruction)

    def test_the_writer_is_told_the_exact_json_shape_it_must_return(self) -> None:
        """The runtime parses this; a free-form answer cannot be parsed."""
        instruction = self.config.project.agents["literature-draft-writer"].instruction
        self.assertIn('"draft_id"', instruction)
        self.assertIn("wiki_document", instruction)

    def test_the_preset_declares_no_duplicate_agent_names(self) -> None:
        """The whole directory is one namespace; a duplicate fails the load."""
        names: list[str] = []
        for path in sorted((KIT_ROOT / "libs" / "workflow-libs").glob("*.yaml")):
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            names.extend(document.get("agents") or {})
        self.assertEqual(len(names), len(set(names)))

    def test_with_agent_pins_the_config_to_one_definition(self) -> None:
        pinned = self.config.with_agent("literature-searcher")
        self.assertEqual(pinned.agent.name, "literature-searcher")
        self.assertEqual(pinned.agent.allowed_mcp_resources, ("literature-search",))
        self.assertIs(pinned.project, self.config.project, "the project must not be reloaded")

    def test_with_agent_refuses_an_unknown_name(self) -> None:
        from work_agent_runtime.assembly import WorkerConfigError

        with self.assertRaises(WorkerConfigError):
            self.config.with_agent("no-such-agent")


class _Inbox:
    def __init__(self, row: dict) -> None:
        self.row = row
        self.processed: list[str] = []

    def get(self, dedupe_key):
        return self.row if dedupe_key == self.row["dedupe_key"] else None

    def mark_processed(self, dedupe_key):
        self.processed.append(dedupe_key)
        self.row["status"] = "processed"


class _ShellRuntime:
    def __init__(self, row: dict, drafts=None) -> None:
        self.inbox = _Inbox(row)
        self.drafts = drafts or FakeDraftBox()


class WorkflowShellTests(unittest.TestCase):
    """A workflow writes its own draft; the shell must not write a second one."""

    def _row(self) -> dict:
        return {
            "dedupe_key": "node-1:evt-1",
            "target_id": "node-1",
            "event_id": "evt-1",
            "agent_definition": "",
            "command_text": "summarise the RAG papers",
            "status": "queued",
        }

    def test_the_workflow_receives_the_rows_instruction(self) -> None:
        seen: list[tuple[str, str]] = []

        class _Result:
            status = "completed"
            draft_id = "draft-1"

        def workflow(prompt, target_id, execution_id):
            seen.append((prompt, target_id, execution_id))
            return _Result()

        runtime = _ShellRuntime(self._row())
        run_one_queued(runtime, agent=None, dedupe_key="node-1:evt-1", workflow=workflow)
        self.assertEqual(
            seen, [("summarise the RAG papers", "node-1", "node-1:evt-1")]
        )

    def test_no_second_draft_is_written(self) -> None:
        """The executor already wrote through `final_writer`."""
        written: list[tuple[str, str]] = []

        class _Drafts(FakeDraftBox):
            def write(self, *, target_id, payload):
                written.append((target_id, payload))
                return "draft-second"

        class _Result:
            status = "completed"
            draft_id = "draft-from-workflow"

        runtime = _ShellRuntime(self._row(), drafts=_Drafts())
        results = run_one_queued(
            runtime, agent=None, dedupe_key="node-1:evt-1", workflow=lambda p, t, e: _Result()
        )
        self.assertEqual(written, [], "the workflow wrote the draft; the shell must not")
        self.assertEqual(results[0]["draft_id"], "draft-from-workflow")
        self.assertEqual(runtime.inbox.processed, ["node-1:evt-1"])

    def test_a_failed_workflow_leaves_the_row_queued(self) -> None:
        class _Result:
            status = "failed"
            draft_id = None
            error_code = "child_agent_failed"

        runtime = _ShellRuntime(self._row())
        results = run_one_queued(
            runtime, agent=None, dedupe_key="node-1:evt-1", workflow=lambda p, t, e: _Result()
        )
        self.assertEqual(runtime.inbox.processed, [])
        self.assertEqual(results[0]["status"], "failed")
        self.assertEqual(results[0]["error_code"], "child_agent_failed")


if __name__ == "__main__":
    unittest.main()
