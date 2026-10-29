"""Runtime wiring tests: what the worker actually hands to fast-agent (ai4-349h).

These tests put a stand-in ``fast_agent`` package into ``sys.modules`` and assert
the decorator kwargs. That is the only seam where "declared in YAML" and "reached
the framework" can be told apart: every earlier bug in this area looked correct in
the loader and produced an agent with no tools.

The suite never calls a model. ``FakeAgent.send`` returns a fixed string and the
session manager records what it was asked to do.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import fast_agent_doubles as doubles
from centre_fixtures import ENVIRON, build_tree
from task_agent_worker.config import WorkerSettings

# `task_agent_worker.runtime` imports fast_agent lazily, so installing the double
# before the first runtime call is enough — but the module itself is imported at
# module scope here for the type of `RuntimeRequest`, which is fine.
from task_agent_worker.runtime import FastAgentDeepSeekRuntime


class _RuntimeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.tree = build_tree(root / "centre")
        self.home = root / "home"
        self.manager = doubles.FakeSessionManager()
        self.agent = doubles.FakeAgent(response="verdict appended")
        self.addCleanup(doubles.remove)
        self.settings = WorkerSettings(
            api_key="sk-test",
            base_url="https://api.invalid/v1",
            model="deepseek-chat",
            home=self.home,
            session_dir="sessions",
            connection_scope="centre",
        )
        self.recorded = doubles.install(self.manager, self.agent)
        self.runtime = self.make_runtime()

    def make_runtime(self, **overrides: str) -> FastAgentDeepSeekRuntime:
        from task_agent_worker.assembly import load_centre_config

        config = load_centre_config({**ENVIRON, **overrides}, root=self.tree)
        return FastAgentDeepSeekRuntime(self.settings, config)


class AgentWiringTests(_RuntimeTestCase):
    def test_every_step_in_the_chain_is_registered(self) -> None:
        self.runtime.run(doubles.Request())
        self.assertEqual([item["name"] for item in self.recorded.agents], ["step-read", "step-write"])

    def test_servers_come_from_the_definition_not_from_the_catalog(self) -> None:
        self.runtime.run(doubles.Request())
        self.assertEqual(self.recorded.agent("step-read")["servers"], ["research-mapping", "research-wiki"])
        self.assertEqual(self.recorded.agent("step-write")["servers"], ["research-mapping", "email-service"])

    def test_the_tool_allowlist_reaches_the_framework(self) -> None:
        self.runtime.run(doubles.Request())
        self.assertEqual(
            self.recorded.agent("step-read")["tools"],
            {
                "research-mapping": ["list_reviewable_candidates"],
                "research-wiki": ["list_reviewable_wiki_candidates"],
            },
        )
        self.assertEqual(
            self.recorded.agent("step-write")["tools"]["research-mapping"], ["append_prereview_log"]
        )

    def test_skills_are_explicitly_empty(self) -> None:
        # Omitting `skills` is not the same as `skills=[]`: the default is
        # fast-agent's SKILLS_DEFAULT sentinel, which loads whatever the context or
        # home directory holds. An unattended worker must run none.
        self.runtime.run(doubles.Request())
        for item in self.recorded.agents:
            with self.subTest(agent=item["name"]):
                self.assertEqual(item["skills"], [])

    def test_an_agent_with_no_resources_gets_an_empty_server_list_not_an_omitted_one(self) -> None:
        self.tree.joinpath("definitions", "centre-prereview.yaml").write_text(
            "\n".join(
                [
                    "version: 1.0.0",
                    "agents:",
                    "  solo:",
                    "    identity: only step",
                    "    instruction: do nothing",
                    "    model: configure-in-your-own-environment",
                    "    allowed_mcp_resources: []",
                    "    resources: []",
                    "workflows:",
                    "  centre-prereview:",
                    "    type: Chain",
                    "    sequence: [solo]",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.make_runtime().run(doubles.Request())
        self.assertEqual(self.recorded.agent("solo")["servers"], [])
        self.assertEqual(self.recorded.agent("solo")["tools"], {})

    def test_the_model_falls_back_to_the_environment_on_a_placeholder(self) -> None:
        self.runtime.run(doubles.Request())
        self.assertEqual(self.recorded.agent("step-read")["model"], "openai.deepseek-chat")

    def test_a_real_model_name_in_the_definition_beats_the_environment(self) -> None:
        # One step pinned to a different model without touching `.env`; the other
        # keeps falling back to `SCIWEAVE_WORKER_MODEL`.
        path = self.tree / "definitions" / "centre-prereview.yaml"
        path.write_text(
            path.read_text(encoding="utf-8").replace("model: deepseek-chat", "model: deepseek-reasoner"),
            encoding="utf-8",
        )
        runtime = self.make_runtime()
        self.assertEqual(runtime.model_for("step-write"), "deepseek-reasoner")
        self.assertEqual(runtime.model_for("step-read"), "deepseek-chat")
        runtime.run(doubles.Request())
        self.assertEqual(self.recorded.agent("step-write")["model"], "openai.deepseek-reasoner")

    def test_the_instruction_comes_from_the_definition_with_the_rule_set_filled_in(self) -> None:
        self.runtime.run(doubles.Request())
        self.assertEqual(self.recorded.agent("step-read")["instruction"], "read the snapshot, then stop")
        self.assertEqual(
            self.recorded.agent("step-write")["instruction"],
            "append the verdict for rule set 1.0.0",
        )

    def test_editing_the_instruction_in_the_yaml_changes_what_the_framework_receives(self) -> None:
        # The whole point of a description layer: no Python edit, no rebuild.
        path = self.tree / "definitions" / "centre-prereview.yaml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "read the snapshot, then stop", "take exactly one snapshot and report it"
            ),
            encoding="utf-8",
        )
        self.make_runtime().run(doubles.Request())
        self.assertEqual(
            self.recorded.agent("step-read")["instruction"], "take exactly one snapshot and report it"
        )

    def test_the_chain_is_registered_with_the_configured_sequence(self) -> None:
        self.runtime.run(doubles.Request())
        chain = self.recorded.chain
        self.assertEqual(chain["name"], "centre-prereview")
        self.assertEqual(chain["sequence"], ["step-read", "step-write"])
        self.assertTrue(chain["cumulative"])
        self.assertTrue(chain["default"])


class ConfigFileTests(_RuntimeTestCase):
    def test_the_generated_config_file_is_written_where_fast_agent_reads_it(self) -> None:
        self.runtime.run(doubles.Request())
        config_path = Path(self.recorded.fast_agent_kwargs["config_path"])
        self.assertEqual(config_path, self.home / "fast-agent.yaml")
        body = config_path.read_text(encoding="utf-8")
        self.assertIn("mcp:", body)
        self.assertIn("research-mapping:", body)
        self.assertIn(ENVIRON["RESEARCH_MAPPING_MCP_URL"], body)

    def test_the_config_file_holds_no_token_even_when_one_is_configured(self) -> None:
        # Cards list the token variable, but nothing here turns it into a header;
        # writing it into a file the model's home directory holds would leak it.
        self.make_runtime(RESEARCH_MAPPING_MCP_TOKEN="super-secret-token").run(doubles.Request())
        body = (self.home / "fast-agent.yaml").read_text(encoding="utf-8")
        self.assertNotIn("super-secret-token", body)


class SessionTests(_RuntimeTestCase):
    def test_a_fresh_run_creates_a_session_carrying_the_workflow_and_rule_set(self) -> None:
        self.runtime.run(doubles.Request())
        session_id, metadata = self.manager.created[0]
        self.assertEqual(session_id, "session-1")
        self.assertEqual(metadata["workflow"], "centre-prereview")
        self.assertEqual(metadata["rule_set_version"], "1.0.0")
        self.assertEqual(metadata["connection_scope"], "centre")

    def test_a_resume_restores_the_chain_rather_than_a_single_agent(self) -> None:
        self.runtime.resume(doubles.Request())
        self.assertEqual(self.manager.resumed, ["session-1"])
        self.assertEqual(self.manager.created, [])

    def test_a_failed_restore_is_reported_rather_than_silently_continued(self) -> None:
        self.manager.restore_fails = True
        outcome = self.runtime.resume(doubles.Request())
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_summary, "session_restore_failed")

    def test_the_chain_receives_the_request_text_once_not_once_per_step(self) -> None:
        self.runtime.run(doubles.Request())
        self.assertEqual(self.agent.sent, ["run one prereview round"])


class OutcomeTests(_RuntimeTestCase):
    def test_a_completed_run_names_the_workflow_it_ran(self) -> None:
        outcome = self.runtime.run(doubles.Request())
        self.assertEqual(outcome.status, "completed")
        self.assertIn("centre-prereview", outcome.result_summary or "")

    def test_the_api_key_never_appears_in_the_summary(self) -> None:
        self.agent.response = "used sk-test and finished"
        outcome = self.runtime.run(doubles.Request())
        self.assertNotIn("sk-test", outcome.result_summary or "")
        self.assertIn("[redacted]", outcome.result_summary or "")

    def test_a_missing_session_manager_is_a_failure_not_a_silent_noop(self) -> None:
        doubles.install(self.manager, self.agent, recorded=self.recorded, context=False)
        outcome = self.runtime.run(doubles.Request())
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_summary, "session_manager_unavailable")

    def test_a_raising_agent_becomes_a_stable_error_code(self) -> None:
        self.agent.error = RuntimeError("model exploded")
        outcome = self.runtime.run(doubles.Request())
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_summary, "fast_agent_runtime_error")

    def test_a_raising_agent_is_logged_with_its_stack(self) -> None:
        """A failed run must leave a trace, not only a bare error code."""
        import logging

        self.agent.error = RuntimeError("model exploded")
        with self.assertLogs("task_agent_worker", level="ERROR") as captured:
            self.runtime.run(doubles.Request())
        joined = "\n".join(captured.output)
        self.assertIn("fast-agent runtime failed", joined)
        # ``logger.exception`` records the traceback, so the cause is visible.
        self.assertIn("model exploded", joined)
        self.assertIn("Traceback", joined)


class ConfigurationAtStartupTests(unittest.TestCase):
    def test_a_broken_definition_fails_when_the_runtime_is_built_not_on_first_run(self) -> None:
        from task_agent_worker.assembly import CentreConfigError, load_centre_config

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree = build_tree(root / "centre")
            (tree / "definitions" / "centre-prereview.yaml").write_text("version: 2.0.0\n", encoding="utf-8")
            with self.assertRaises(CentreConfigError) as caught:
                load_centre_config(dict(ENVIRON), root=tree)
        self.assertIn("unsupported_config_version", caught.exception.detail)

    def test_the_runtime_refuses_to_build_without_a_model(self) -> None:
        from task_agent_worker.config import WorkerSettings

        with tempfile.TemporaryDirectory() as tmp:
            settings = WorkerSettings(
                api_key="sk-test",
                base_url="https://api.invalid/v1",
                model="",
                home=Path(tmp),
                session_dir="sessions",
                connection_scope="centre",
            )
            with self.assertRaises(ValueError) as caught:
                FastAgentDeepSeekRuntime(settings, None)
        self.assertIn("SCIWEAVE_WORKER_MODEL", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
