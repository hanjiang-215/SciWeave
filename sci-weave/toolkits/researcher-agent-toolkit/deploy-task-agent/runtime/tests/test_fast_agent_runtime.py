"""The real fast-agent runtime and its factory (ai4-g1km).

No test calls a model: ``fast_agent`` is replaced in ``sys.modules`` with a
double, so these cases pin the wiring (session creation, resume, redaction,
error mapping) without a key or a network.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# `discover -s tests` puts this directory on sys.path; `-m unittest
# tests.test_x` makes it a namespace package. Both spellings have to work.
try:
    from fast_agent_doubles import (
        FakeAgent as _FakeAgent,
        FakeSessionManager as _FakeSessionManager,
        Request as _Request,
        install as _install_fake,
        make_unimportable,
        pop,
        remove as _remove_fake_fast_agent,
    )
except ImportError:  # pragma: no cover
    from tests.fast_agent_doubles import (  # type: ignore[no-redef]
        FakeAgent as _FakeAgent,
        FakeSessionManager as _FakeSessionManager,
        Request as _Request,
        install as _install_fake,
        make_unimportable,
        remove as _remove_fake_fast_agent,
    )

from work_agent_runtime.assembly import WorkerConfigError
from work_agent_runtime.fast_agent_runtime import (
    AgentOutcome,
    FastAgentDeepSeekRuntime,
    FastAgentSettings,
    PassthroughAgentRuntime,
    build_agent_runtime,
)


class SettingsTests(unittest.TestCase):
    def _settings(self, **overrides) -> FastAgentSettings:
        values = dict(
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            home=Path("."),
        )
        values.update(overrides)
        return FastAgentSettings(**values)

    def test_a_missing_or_placeholder_key_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self._settings(api_key=None).validate_for_model_call()
        with self.assertRaises(ValueError):
            self._settings(api_key="replace-with-your-key").validate_for_model_call()

    def test_a_plain_http_base_url_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self._settings(base_url="http://api.deepseek.com").validate_for_model_call()

    def test_an_empty_model_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self._settings(model="  ").validate_for_model_call()

    def test_a_session_dir_cannot_escape_the_home(self) -> None:
        # Each of these is only rejected by a textual check: on POSIX `Path` treats
        # "C:/absolute" as relative and "..\..\outside" as a single part (ai4-grlc).
        for escaping in ("../outside", r"..\..\outside", "C:/absolute", r"C:\absolute", "", "  "):
            with self.subTest(session_dir=escaping):
                with self.assertRaises(ValueError):
                    self._settings(session_dir=escaping).validate_for_model_call()

    def test_a_relative_session_subdirectory_is_accepted(self) -> None:
        for allowed in ("sessions", "sessions/worker", "run-1/sessions"):
            with self.subTest(session_dir=allowed):
                self._settings(session_dir=allowed).validate_for_model_call()


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "agent-home"
        self.manager = _FakeSessionManager()
        self.addCleanup(_remove_fake_fast_agent)

    def _runtime(self, **overrides) -> FastAgentDeepSeekRuntime:
        values = dict(
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            home=self.home,
        )
        values.update(overrides)
        return FastAgentDeepSeekRuntime(FastAgentSettings(**values))

    def test_a_run_creates_a_session_and_returns_the_summary(self) -> None:
        agent = _FakeAgent("  the   dataset has 3 rows ")
        _install_fake(self.manager, agent)

        outcome = self._runtime().run(_Request())

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(outcome.result_summary, "fast-agent completed: the dataset has 3 rows")
        self.assertEqual(agent.sent, ["summarise the dataset"])
        self.assertEqual(self.manager.created, [("session-1", {"connection_scope": "local"})])
        self.assertTrue((self.home / "fast-agent.yaml").exists())

    def test_the_api_key_is_redacted_from_the_summary(self) -> None:
        agent = _FakeAgent("used sk-secret-key for the call")
        _install_fake(self.manager, agent)

        outcome = self._runtime(api_key="sk-secret-key").run(_Request())

        self.assertNotIn("sk-secret-key", outcome.result_summary)
        self.assertIn("[redacted]", outcome.result_summary)

    def test_resume_restores_the_session(self) -> None:
        agent = _FakeAgent("resumed")
        _install_fake(self.manager, agent)

        outcome = self._runtime().resume(_Request())

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(outcome.result_summary, "fast-agent resumed: resumed")
        self.assertEqual(self.manager.resumed, ["session-1"])
        self.assertEqual(self.manager.created, [])

    def test_a_failed_restore_is_reported(self) -> None:
        self.manager.restore_fails = True
        _install_fake(self.manager, _FakeAgent())

        outcome = self._runtime().resume(_Request())

        self.assertEqual((outcome.status, outcome.error_summary), ("failed", "session_restore_failed"))

    def test_a_missing_session_manager_is_reported(self) -> None:
        _install_fake(self.manager, _FakeAgent(), context=False)

        outcome = self._runtime().run(_Request())

        self.assertEqual(
            (outcome.status, outcome.error_summary), ("failed", "session_manager_unavailable")
        )

    def test_a_provider_error_becomes_a_stable_failure(self) -> None:
        _install_fake(self.manager, _FakeAgent(error=RuntimeError("429 rate limited")))

        outcome = self._runtime().run(_Request())

        self.assertEqual((outcome.status, outcome.error_summary), ("failed", "fast_agent_runtime_error"))

    def test_a_missing_fast_agent_package_is_reported(self) -> None:
        # Now that the dependency is installed, dropping it from sys.modules only
        # makes the import reload from disk. A None entry makes ``import
        # fast_agent`` raise ImportError, which is the state a deployment without
        # the extra would be in.
        make_unimportable()
        self.addCleanup(pop, "fast_agent")

        outcome = self._runtime().run(_Request())

        self.assertEqual((outcome.status, outcome.error_summary), ("failed", "fast_agent_unavailable"))

    def test_an_empty_response_is_not_an_empty_summary(self) -> None:
        _install_fake(self.manager, _FakeAgent("   "))

        outcome = self._runtime().run(_Request())

        self.assertEqual(outcome.result_summary, "fast-agent completed: empty model response")

    def test_cancel_returns_a_cancelled_outcome(self) -> None:
        self.assertEqual(self._runtime().cancel("exec-1").status, "cancelled")


class ConfiguredAgentTests(unittest.TestCase):
    """ai4-z3yq, second acceptance criterion.

    The point is not "the loader returns an object" — `test_agent_config.py`
    already covers that. It is that the instruction the *framework* receives
    comes from the YAML, so editing `agent-definitions/agents/*.yaml` changes
    what the model is told. Before this, `@fast.agent(instruction=...)` was a
    literal in `fast_agent_runtime.py` and no YAML was read on this path.
    """

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.manager = _FakeSessionManager()
        self.recorded: list[dict] = []
        self.addCleanup(_remove_fake_fast_agent)

    def _runtime_with(self, instruction: str, *, agent_name: str = "researcher-task-agent"):
        from work_agent_runtime.config import load_config
        from work_agent_runtime.resources import ResourceRegistry

        project = load_config(
            {
                "agents": {
                    agent_name: {
                        "identity": "test identity",
                        "instruction": instruction,
                        "model": "deepseek-chat",
                        "allowed_mcp_resources": [],
                        "resources": [],
                    }
                },
                "workflows": {},
            }
        )
        config = type(
            "WorkerConfigStub",
            (),
            {
                "agent": project.agents[agent_name],
                "agent_name": agent_name,
                "project": project,
                "resources": ResourceRegistry(),
                "mcp": None,
                "sources": {},
            },
        )()
        return FastAgentDeepSeekRuntime(
            FastAgentSettings(
                api_key="sk-test",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                home=Path(self._tmp.name) / "home",
            ),
            config,
        )

    def test_the_instruction_reaches_the_framework_from_the_configuration(self) -> None:
        _install_fake(self.manager, _FakeAgent(), recorded=self.recorded)
        runtime = self._runtime_with("Cite every claim or mark it unverified.")
        outcome = runtime.run(_Request())
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(len(self.recorded), 1)
        self.assertIn("Cite every claim or mark it unverified.", self.recorded[0]["instruction"])

    def test_editing_the_instruction_changes_what_the_framework_receives(self) -> None:
        _install_fake(self.manager, _FakeAgent(), recorded=self.recorded)
        self._runtime_with("first instruction").run(_Request())
        self.recorded.clear()
        self._runtime_with("second instruction").run(_Request())
        self.assertIn("second instruction", self.recorded[0]["instruction"])
        self.assertNotIn("first instruction", self.recorded[0]["instruction"])

    def test_the_agent_name_comes_from_the_definition_not_the_task_node(self) -> None:
        """The name used to be `worker-{task_node_id}`, so it changed per task.

        That made the agent identity un-pinnable: session history and (later)
        `mcp.servers` could never be attached to a definition.
        """
        _install_fake(self.manager, _FakeAgent(), recorded=self.recorded)
        self._runtime_with("instruction", agent_name="researcher-task-agent").run(_Request())
        self.assertEqual(self.recorded[0]["name"], "researcher-task-agent")
        self.assertNotIn("node-1", self.recorded[0]["name"])


class FactoryTests(unittest.TestCase):
    def _env(self, **overrides) -> dict:
        values = {
            "DEEPSEEK_API_KEY": "sk-test",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "DEEPSEEK_MODEL": "deepseek-chat",
            "SCIWEAVE_AGENT_ID": "researcher-task-agent",
            # The shipped definition grants MCP resources, and a missing URL is
            # a startup error (ai4-x0ay) rather than a silently tool-less agent.
            "RESEARCH_MAPPING_MCP_URL": "https://mapping.invalid/mcp",
            "LLM_WIKI_MCP_URL": "https://wiki.invalid/mcp",
            "DRAFT_BUFFER_MCP_URL": "https://buffer.invalid/mcp",
        }
        values.update(overrides)
        return values

    def test_passthrough_needs_an_explicit_switch(self) -> None:
        runtime = build_agent_runtime(
            {
                "SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME": "1",
                "SCIWEAVE_AGENT_ID": "researcher-task-agent",
            }
        )
        self.assertIsInstance(runtime, PassthroughAgentRuntime)

    def test_passthrough_still_loads_the_configuration(self) -> None:
        """The workflow wiring must be exercisable without a model key.

        The passthrough ignores the model, but it has to know which workflow and
        which agents were configured — otherwise "does the worker run the
        configured workflow" could only ever be tested with a real key, which is
        why that wiring stayed broken (ai4-x0ay).
        """
        runtime = build_agent_runtime(
            {
                "SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME": "1",
                "SCIWEAVE_AGENT_ID": "researcher-task-agent",
            }
        )
        self.assertEqual(runtime.config.agent.name, "researcher-task-agent")
        self.assertIn("literature-agent", runtime.config.project.workflows)

    def test_passthrough_still_refuses_an_unknown_agent(self) -> None:
        from work_agent_runtime import WorkerConfigError

        with self.assertRaises(WorkerConfigError):
            build_agent_runtime(
                {
                    "SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME": "1",
                    "SCIWEAVE_AGENT_ID": "no-such-agent",
                }
            )

    def test_a_missing_key_fails_instead_of_falling_back(self) -> None:
        with self.assertRaises(ValueError):
            build_agent_runtime({})

    def test_a_missing_key_is_reported_before_a_missing_config(self) -> None:
        """Both are hard stops; the key one is the one the researcher can act on."""
        with self.assertRaises(ValueError) as caught:
            build_agent_runtime({"SCIWEAVE_AGENT_ID": "researcher-task-agent"})
        self.assertIn("DEEPSEEK_API_KEY", str(caught.exception))

    def test_a_configured_environment_builds_the_real_runtime(self) -> None:
        runtime = build_agent_runtime(self._env())
        self.assertIsInstance(runtime, FastAgentDeepSeekRuntime)
        self.assertEqual(runtime.settings.model, "deepseek-chat")

    def test_the_factory_loads_the_shipped_configuration(self) -> None:
        """ai4-z3yq: before this, `build_agent_runtime` read six scalars.

        The three libs directories and `agent-definitions/` were described in
        the README and copied by `install.sh`, and no code path read them.
        """
        runtime = build_agent_runtime(self._env())
        self.assertIsNotNone(runtime.config)
        self.assertEqual(runtime.config.agent_name, "researcher-task-agent")
        self.assertEqual(
            sorted(runtime.config.project.workflows),
            ["agents-as-tools-example", "literature-agent", "orchestrator-example", "parallel-example", "router-example"],
        )

    def test_the_factory_refuses_an_agent_id_no_definition_declares(self) -> None:
        with self.assertRaises(WorkerConfigError) as caught:
            build_agent_runtime(self._env(SCIWEAVE_AGENT_ID="nobody-declares-this"))
        self.assertEqual(caught.exception.variable, "SCIWEAVE_AGENT_ID")
        self.assertIn("researcher-task-agent", str(caught.exception))

    def test_the_factory_refuses_a_missing_shipped_directory(self) -> None:
        with TemporaryDirectory() as empty:
            with self.assertRaises(WorkerConfigError) as caught:
                build_agent_runtime(self._env(MCP_LIBS_PATH=str(Path(empty) / "not-there")))
        self.assertEqual(caught.exception.variable, "MCP_LIBS_PATH")
        self.assertIn(str(Path(empty) / "not-there"), str(caught.exception))


class PassthroughTests(unittest.TestCase):
    def test_the_passthrough_is_deterministic(self) -> None:
        runtime = PassthroughAgentRuntime()
        outcome = runtime.run(_Request())
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(outcome.result_summary, "passthrough: summarise the dataset")
        self.assertEqual(runtime.resume(_Request()).status, "completed")
        self.assertEqual(runtime.cancel("exec-1").status, "cancelled")


if __name__ == "__main__":
    unittest.main()
