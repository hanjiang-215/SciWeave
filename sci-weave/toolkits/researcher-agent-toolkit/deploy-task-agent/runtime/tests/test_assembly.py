"""The worker's configuration assembly (ai4-z3yq).

Before `assembly.py` existed, `config.py`, `resources.py` and `mcp_resources.py`
could all load the researcher's YAML and nothing in `runtime/src` or
`service-template/` ever called them. These tests pin the chain
``environment -> WorkerConfig``, and they assert on the *shipped* directories so
that a broken shipped file fails here rather than on a researcher's machine.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from work_agent_runtime.assembly import WorkerConfigError, kit_root, load_worker_config
from work_agent_runtime.fast_agent_runtime import build_agent_runtime

# `discover -s tests` puts this directory on sys.path; `-m unittest
# tests.test_assembly` makes it a namespace package. Both spellings have to work.
try:
    from fast_agent_doubles import FakeAgent, FakeSessionManager, Request, install, remove
except ImportError:  # pragma: no cover
    from tests.fast_agent_doubles import (  # type: ignore[no-redef]
        FakeAgent,
        FakeSessionManager,
        Request,
        install,
        remove,
    )

KIT_ROOT = kit_root()


def _env(**overrides) -> dict[str, str]:
    values = {"SCIWEAVE_AGENT_ID": "researcher-task-agent"}
    values.update(overrides)
    return values


class ShippedConfigurationTests(unittest.TestCase):
    """The kit as installed: no variables set beyond the agent id."""

    def setUp(self) -> None:
        self.config = load_worker_config(_env())

    def test_the_selected_agent_is_the_one_sciweave_agent_id_names(self) -> None:
        self.assertEqual(self.config.agent_name, "researcher-task-agent")
        self.assertEqual(self.config.agent.identity, "通用科研任务 Agent")

    def test_the_instruction_is_not_the_hardcoded_sentence(self) -> None:
        """The old runtime used a literal; this asserts the YAML is the source."""
        self.assertIn("Complete the assigned research task", self.config.agent.instruction)
        self.assertNotIn("SciWeave researcher-side Task Agent", self.config.agent.instruction)

    def test_the_mcp_cards_are_loaded_and_the_agent_only_names_real_ones(self) -> None:
        declared = {resource.name for resource in self.config.mcp.resources}
        self.assertIn("literature-search", declared)
        self.assertLessEqual(set(self.config.agent.allowed_mcp_resources), declared)

    def test_the_agent_resources_are_addressable_by_reference(self) -> None:
        """`libs/agent-libs/` holds resources an agent's `resources:` list names."""
        identifiers = set(self.config.resources.references())
        self.assertIn("research.prompt@1.0.0", identifiers)
        resource = self.config.resource("research.prompt@1.0.0")
        self.assertEqual(resource.kind, "prompt")

    def test_the_workflow_libs_are_loaded(self) -> None:
        self.assertEqual(
            sorted(self.config.project.workflows),
            ["agents-as-tools-example", "orchestrator-example", "parallel-example", "router-example"],
        )

    def test_every_source_directory_is_reported(self) -> None:
        """A researcher debugging "my YAML is ignored" needs to see what was read."""
        self.assertEqual(
            sorted(self.config.sources),
            ["AGENT_DEFINITIONS_PATH", "WORKFLOW_LIBS_PATH"],
        )
        for path in self.config.sources.values():
            self.assertTrue(Path(path).is_absolute(), path)

    def test_the_assembly_does_not_require_the_home_directory(self) -> None:
        """`kit_root()` derives from `__file__`, so it works from any cwd."""
        self.assertTrue((KIT_ROOT / "libs" / "mcp-libs").is_dir())


class StrictnessTests(unittest.TestCase):
    """Every failure names the variable and the directory.

    The failure a researcher actually hits is a mistyped path; a bare
    ``[invalid_document]`` from four possible roots is not actionable.
    """

    def test_an_unset_agent_id_is_refused(self) -> None:
        with self.assertRaises(WorkerConfigError) as caught:
            load_worker_config({})
        self.assertEqual(caught.exception.variable, "SCIWEAVE_AGENT_ID")

    def test_an_unknown_agent_id_lists_the_known_ones(self) -> None:
        with self.assertRaises(WorkerConfigError) as caught:
            load_worker_config(_env(SCIWEAVE_AGENT_ID="does-not-exist"))
        message = str(caught.exception)
        self.assertIn("does-not-exist", message)
        for known in ("researcher-task-agent", "biology-collaborator", "data-collaborator"):
            self.assertIn(known, message)

    def test_a_missing_shipped_directory_fails_instead_of_falling_back(self) -> None:
        for variable in ("MCP_LIBS_PATH", "AGENT_LIBS_PATH", "WORKFLOW_LIBS_PATH", "AGENT_DEFINITIONS_PATH"):
            with self.subTest(variable=variable), TemporaryDirectory() as empty:
                missing = str(Path(empty) / "absent")
                with self.assertRaises(WorkerConfigError) as caught:
                    load_worker_config(_env(**{variable: missing}))
                self.assertEqual(caught.exception.variable, variable)
                self.assertIn(missing, str(caught.exception))

    def test_an_invalid_definition_names_the_directory_and_the_field(self) -> None:
        """The loader does not carry the file name through `ConfigError`.

        `load_config` reports `config.agents.x.instruction`, so the directory is
        as precise as this layer can be; it is the part a researcher mistyped.
        """
        with TemporaryDirectory() as empty:
            Path(empty, "broken.yaml").write_text(
                "version: 1.0.0\nagents:\n  x:\n    identity: no instruction\n", encoding="utf-8"
            )
            with self.assertRaises(WorkerConfigError) as caught:
                load_worker_config(_env(AGENT_DEFINITIONS_PATH=empty))
        self.assertIn(empty, str(caught.exception))
        self.assertIn("instruction", str(caught.exception))

    def test_two_roots_declaring_the_same_agent_are_refused(self) -> None:
        """Silently letting one win is how a researcher "loses" an edit."""
        with TemporaryDirectory() as empty:
            Path(empty, "dup.yaml").write_text(
                "version: 1.0.0\n"
                "agents:\n"
                "  researcher-task-agent:\n"
                "    identity: duplicate\n"
                "    instruction: shadow the shipped one\n"
                "    model: deepseek-chat\n"
                "    allowed_mcp_resources: []\n"
                "    resources: []\n",
                encoding="utf-8",
            )
            with self.assertRaises(WorkerConfigError) as caught:
                # A *local* root shadows the shipped one by name, which is the
                # arrangement that would otherwise let an edit silently vanish.
                load_worker_config(_env(LOCAL_AGENT_DEFINITIONS_PATH=empty))
        message = str(caught.exception)
        self.assertIn("also defined by", message)
        self.assertIn("researcher-task-agent", message)

    def test_a_local_definition_directory_can_add_an_agent(self) -> None:
        with TemporaryDirectory() as empty:
            Path(empty, "mine.yaml").write_text(
                "version: 1.0.0\n"
                "agents:\n"
                "  my-own-agent:\n"
                "    identity: my own\n"
                "    instruction: do the thing\n"
                "    model: deepseek-chat\n"
                "    allowed_mcp_resources: [research-wiki]\n"
                "    resources: []\n",
                encoding="utf-8",
            )
            config = load_worker_config(
                _env(SCIWEAVE_AGENT_ID="my-own-agent", LOCAL_AGENT_DEFINITIONS_PATH=empty)
            )
        self.assertEqual(config.agent_name, "my-own-agent")
        self.assertEqual(config.agent.instruction, "do the thing")


class EnvironmentTests(unittest.TestCase):
    """Explicit roots win over the shipped defaults, without disabling siblings."""

    def test_an_explicit_path_wins(self) -> None:
        with TemporaryDirectory() as empty:
            Path(empty, "only.yaml").write_text(
                "version: 1.0.0\n"
                "agents:\n"
                "  researcher-task-agent:\n"
                "    identity: overridden\n"
                "    instruction: from my directory\n"
                "    model: deepseek-chat\n"
                "    allowed_mcp_resources: [research-wiki]\n"
                "    resources: []\n",
                encoding="utf-8",
            )
            config = load_worker_config(_env(AGENT_DEFINITIONS_PATH=empty))
        self.assertEqual(config.agent.instruction, "from my directory")

    def test_setting_one_root_does_not_disable_the_others(self) -> None:
        """The bug a naive `setdefault` would introduce: three roots vanish."""
        with TemporaryDirectory() as empty:
            Path(empty, "only.yaml").write_text(
                "version: 1.0.0\n"
                "agents:\n"
                "  researcher-task-agent:\n"
                "    identity: overridden\n"
                "    instruction: still loads the workflow libs\n"
                "    model: deepseek-chat\n"
                "    allowed_mcp_resources: [research-wiki]\n"
                "    resources: []\n",
                encoding="utf-8",
            )
            config = load_worker_config(_env(AGENT_DEFINITIONS_PATH=empty))
        self.assertEqual(len(config.project.workflows), 4)
        self.assertIn("research-wiki", {resource.name for resource in config.mcp.resources})

    def test_the_test_runner_environment_is_not_leaking_in(self) -> None:
        """`load_worker_config` must not read `os.environ` when given a dict."""
        previous = os.environ.get("SCIWEAVE_AGENT_ID")
        os.environ["SCIWEAVE_AGENT_ID"] = "biology-collaborator"
        try:
            config = load_worker_config(_env())
        finally:
            if previous is None:
                os.environ.pop("SCIWEAVE_AGENT_ID", None)
            else:
                os.environ["SCIWEAVE_AGENT_ID"] = previous
        self.assertEqual(config.agent_name, "researcher-task-agent")


class ConfigurationReachesTheModelTests(unittest.TestCase):
    """The acceptance criterion, end to end: edit YAML -> the framework sees it.

    Asserting that `load_worker_config()` returns a good object is not enough —
    `test_agent_config.py` already did that while the whole chain was dead. This
    starts at `build_agent_runtime()` (what the worker calls) and asserts on the
    kwargs `@fast.agent(...)` receives.
    """

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.recorded: list[dict] = []
        install(FakeSessionManager(), FakeAgent("done"), recorded=self.recorded)
        self.addCleanup(remove)

    def _definitions(self, instruction: str, model: str = "deepseek-chat") -> str:
        """A definitions directory holding one agent with a given instruction."""
        directory = Path(self._tmp.name) / f"defs-{abs(hash(instruction)) % 10**8}"
        directory.mkdir()
        (directory / "mine.yaml").write_text(
            "version: 1.0.0\n"
            "agents:\n"
            "  researcher-task-agent:\n"
            "    identity: edited\n"
            f"    instruction: {instruction}\n"
            f"    model: {model}\n"
            "    allowed_mcp_resources: [research-wiki]\n"
            "    resources: []\n",
            encoding="utf-8",
        )
        return str(directory)

    def _env(self, agent_definition_path: str) -> dict:
        return {
            "DEEPSEEK_API_KEY": "sk-test",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "DEEPSEEK_MODEL": "deepseek-chat",
            "SCIWEAVE_AGENT_ID": "researcher-task-agent",
            "AGENT_DEFINITIONS_PATH": agent_definition_path,
            "SCIWEAVE_FAST_AGENT_HOME": str(Path(self._tmp.name) / "home"),
        }

    def test_editing_the_agent_yaml_changes_the_model_instruction(self) -> None:
        runtime = build_agent_runtime(self._env(self._definitions("Always cite the pinned revision.")))
        runtime.run(Request())
        self.assertIn("Always cite the pinned revision.", self.recorded[0]["instruction"])

    def test_two_edits_produce_two_different_instructions(self) -> None:
        build_agent_runtime(self._env(self._definitions("first version"))).run(Request())
        build_agent_runtime(self._env(self._definitions("second version"))).run(Request())
        self.assertIn("first version", self.recorded[0]["instruction"])
        self.assertIn("second version", self.recorded[1]["instruction"])
        self.assertNotIn("first version", self.recorded[1]["instruction"])

    def test_a_model_named_in_the_definition_wins_over_the_environment(self) -> None:
        env = self._env(self._definitions("instruction", model="deepseek-reasoner"))
        build_agent_runtime(env).run(Request())
        self.assertEqual(self.recorded[0]["model"], "openai.deepseek-reasoner")

    def test_a_placeholder_model_falls_back_to_the_environment(self) -> None:
        """The shipped definitions all say `configure-in-your-own-environment`."""
        env = self._env(self._definitions("instruction", model="configure-in-your-own-environment"))
        build_agent_runtime(env).run(Request())
        self.assertEqual(self.recorded[0]["model"], "openai.deepseek-chat")

    def test_the_default_instruction_is_not_compiled_into_the_runtime(self) -> None:
        """Shipping YAML, not a Python constant, decides what the model is told."""
        build_agent_runtime(self._env(str(KIT_ROOT / "agent-definitions" / "agents"))).run(Request())
        instruction = self.recorded[0]["instruction"]
        self.assertIn("Complete the assigned research task", instruction)
        self.assertNotIn("SciWeave researcher-side Task Agent", instruction)


if __name__ == "__main__":
    unittest.main()
