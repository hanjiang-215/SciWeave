"""The real fast-agent runtime and its factory (ai4-g1km).

No test calls a model: ``fast_agent`` is replaced in ``sys.modules`` with a
double, so these cases pin the wiring (session creation, resume, redaction,
error mapping) without a key or a network.
"""

from __future__ import annotations

import sys
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from work_agent_runtime.fast_agent_runtime import (
    AgentOutcome,
    FastAgentDeepSeekRuntime,
    FastAgentSettings,
    PassthroughAgentRuntime,
    build_agent_runtime,
)


@dataclass
class _Request:
    execution_id: str = "exec-1"
    task_node_id: str = "node-1"
    session_id: str = "session-1"
    command_text: str = "summarise the dataset"


class _FakeSessionManager:
    def __init__(self) -> None:
        self.created: list[tuple[str, dict]] = []
        self.resumed: list[str] = []
        self.restore_fails = False

    def create_session_with_id(self, session_id, metadata, metadata_id_key=None):
        self.created.append((session_id, metadata))

    async def resume_session_agents_async(self, agents, session_id, fallback_agent_name=None):
        self.resumed.append(session_id)
        return None if self.restore_fails else agents


class _FakeAgent:
    def __init__(self, response: str = "done", error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.sent: list[str] = []

    async def send(self, text: str) -> str:
        self.sent.append(text)
        if self.error is not None:
            raise self.error
        return self.response


class _FakeContext:
    def __init__(self, manager) -> None:
        self.session_manager = manager


def _install_fake_fast_agent(manager, agent, *, context=True):
    """Put a stand-in ``fast_agent`` package into sys.modules."""

    class _FastAgent:
        def __init__(self, name, **kwargs):
            self.name = name
            self.kwargs = kwargs

        def agent(self, **kwargs):
            def decorator(function):
                return function

            return decorator

        def run(self):
            agent_instance = agent

            class _App:
                def __getattr__(self, item):
                    return agent_instance

            class _Runner:
                async def __aenter__(self):
                    return _App()

                async def __aexit__(self, *exc):
                    return False

            return _Runner()

    package = types.ModuleType("fast_agent")
    package.FastAgent = _FastAgent
    context_module = types.ModuleType("fast_agent.context")
    context_module.get_initialized_context = (
        (lambda: _FakeContext(manager)) if context else (lambda: None)
    )
    sys.modules["fast_agent"] = package
    sys.modules["fast_agent.context"] = context_module


def _remove_fake_fast_agent():
    sys.modules.pop("fast_agent", None)
    sys.modules.pop("fast_agent.context", None)


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
        with self.assertRaises(ValueError):
            self._settings(session_dir="../outside").validate_for_model_call()
        with self.assertRaises(ValueError):
            self._settings(session_dir="C:/absolute").validate_for_model_call()


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
        _install_fake_fast_agent(self.manager, agent)

        outcome = self._runtime().run(_Request())

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(outcome.result_summary, "fast-agent completed: the dataset has 3 rows")
        self.assertEqual(agent.sent, ["summarise the dataset"])
        self.assertEqual(self.manager.created, [("session-1", {"connection_scope": "local"})])
        self.assertTrue((self.home / "fast-agent.yaml").exists())

    def test_the_api_key_is_redacted_from_the_summary(self) -> None:
        agent = _FakeAgent("used sk-secret-key for the call")
        _install_fake_fast_agent(self.manager, agent)

        outcome = self._runtime(api_key="sk-secret-key").run(_Request())

        self.assertNotIn("sk-secret-key", outcome.result_summary)
        self.assertIn("[redacted]", outcome.result_summary)

    def test_resume_restores_the_session(self) -> None:
        agent = _FakeAgent("resumed")
        _install_fake_fast_agent(self.manager, agent)

        outcome = self._runtime().resume(_Request())

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(outcome.result_summary, "fast-agent resumed: resumed")
        self.assertEqual(self.manager.resumed, ["session-1"])
        self.assertEqual(self.manager.created, [])

    def test_a_failed_restore_is_reported(self) -> None:
        self.manager.restore_fails = True
        _install_fake_fast_agent(self.manager, _FakeAgent())

        outcome = self._runtime().resume(_Request())

        self.assertEqual((outcome.status, outcome.error_summary), ("failed", "session_restore_failed"))

    def test_a_missing_session_manager_is_reported(self) -> None:
        _install_fake_fast_agent(self.manager, _FakeAgent(), context=False)

        outcome = self._runtime().run(_Request())

        self.assertEqual(
            (outcome.status, outcome.error_summary), ("failed", "session_manager_unavailable")
        )

    def test_a_provider_error_becomes_a_stable_failure(self) -> None:
        _install_fake_fast_agent(self.manager, _FakeAgent(error=RuntimeError("429 rate limited")))

        outcome = self._runtime().run(_Request())

        self.assertEqual((outcome.status, outcome.error_summary), ("failed", "fast_agent_runtime_error"))

    def test_a_missing_fast_agent_package_is_reported(self) -> None:
        _remove_fake_fast_agent()

        outcome = self._runtime().run(_Request())

        self.assertEqual((outcome.status, outcome.error_summary), ("failed", "fast_agent_unavailable"))

    def test_an_empty_response_is_not_an_empty_summary(self) -> None:
        _install_fake_fast_agent(self.manager, _FakeAgent("   "))

        outcome = self._runtime().run(_Request())

        self.assertEqual(outcome.result_summary, "fast-agent completed: empty model response")

    def test_cancel_returns_a_cancelled_outcome(self) -> None:
        self.assertEqual(self._runtime().cancel("exec-1").status, "cancelled")


class FactoryTests(unittest.TestCase):
    def test_passthrough_needs_an_explicit_switch(self) -> None:
        runtime = build_agent_runtime({"SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME": "1"})
        self.assertIsInstance(runtime, PassthroughAgentRuntime)

    def test_a_missing_key_fails_instead_of_falling_back(self) -> None:
        with self.assertRaises(ValueError):
            build_agent_runtime({})

    def test_a_configured_environment_builds_the_real_runtime(self) -> None:
        runtime = build_agent_runtime(
            {
                "DEEPSEEK_API_KEY": "sk-test",
                "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
                "DEEPSEEK_MODEL": "deepseek-chat",
            }
        )
        self.assertIsInstance(runtime, FastAgentDeepSeekRuntime)
        self.assertEqual(runtime.settings.model, "deepseek-chat")


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
