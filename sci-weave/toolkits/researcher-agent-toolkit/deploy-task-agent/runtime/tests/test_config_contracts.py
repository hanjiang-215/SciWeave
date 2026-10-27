"""Config-layer contracts that the shipped kit must satisfy to be usable (ai4-4r0h).

Every test here encodes a defect found by actually running the bundled config:
the loader returned an empty project, dropped a key, or could not read the
directory it advertises. They are the regression net for "the researcher follows
the README and gets nothing".
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import yaml

from work_agent_runtime import ConfigError, load_config, load_mcp_registry, load_workflow_libs, load_workflow_yaml

KIT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_LIBS = KIT_ROOT / "libs" / "workflow-libs"
AGENT_DEFINITIONS = KIT_ROOT / "agent-definitions" / "agents"


def bundled_mcp_names() -> frozenset[str]:
    """Server names as the kit itself declares them, not a hand-maintained list."""
    registry = load_mcp_registry(standard_mcp_libs=KIT_ROOT / "libs" / "mcp-libs", local_mcp_libs="")
    return frozenset(item.name for item in registry.resources)


class NoDefinitionsTests(unittest.TestCase):
    def test_a_directory_of_flat_agent_files_is_an_error_not_an_empty_project(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "solo.yaml").write_text(
                "name: solo\nidentity: solo\ninstruction: do it\nmodel: fake\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ConfigError, "no_definitions"):
                load_workflow_yaml(root)

    def test_a_single_flat_file_is_an_error_too(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "solo.yaml"
            path.write_text("name: solo\nidentity: solo\ninstruction: do it\nmodel: fake\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "no_definitions"):
                load_workflow_yaml(path)


class UnknownFieldTests(unittest.TestCase):
    AGENTS = {
        "router": {"identity": "r", "instruction": "r", "model": "fake", "allowed_mcp_resources": [], "resources": []},
        "writer": {"identity": "w", "instruction": "w", "model": "fake", "allowed_mcp_resources": [], "resources": []},
    }
    WORKFLOW = {"type": "Router", "entry_agent": "router", "sub_agents": ["router"], "summarizer": "router", "final_writer": "writer"}

    def _raw(self, **overrides):
        return {
            "agents": dict(self.AGENTS),
            "workflows": {"main": dict(self.WORKFLOW)},
            **overrides,
        }

    def test_unknown_top_level_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "unknown_field"):
            load_config(self._raw(unknown_top=1))

    def test_unknown_agent_key_is_rejected(self) -> None:
        raw = self._raw()
        raw["agents"]["writer"] = {**raw["agents"]["writer"], "temperatur": 0.2}
        with self.assertRaisesRegex(ConfigError, "unknown_field"):
            load_config(raw)

    def test_unknown_workflow_key_is_rejected(self) -> None:
        raw = self._raw()
        raw["workflows"]["main"] = {**raw["workflows"]["main"], "bogus_key": 123}
        with self.assertRaisesRegex(ConfigError, "unknown_field"):
            load_config(raw)

    def test_declared_keys_still_load(self) -> None:
        raw = self._raw(version="1.0.0", name="demo")
        raw["agents"]["router"]["references"] = ["ref"]
        raw["agents"]["router"]["allowed_domain_mcps"] = []
        config = load_config(raw)
        self.assertIn("main", config.workflows)


class WorkflowLibsPathTests(unittest.TestCase):
    def _write(self, root: Path, name: str, body: str) -> None:
        (root / name).write_text(body, encoding="utf-8")

    def test_env_standard_path_is_loaded_and_local_overrides_it(self) -> None:
        with TemporaryDirectory() as standard_dir, TemporaryDirectory() as local_dir:
            standard, local = Path(standard_dir), Path(local_dir)
            self._write(
                standard,
                "base.yaml",
                """
version: 1.0.0
agents:
  router: {identity: shipped, instruction: shipped, model: fake, allowed_mcp_resources: [], resources: []}
  writer: {identity: w, instruction: w, model: fake, allowed_mcp_resources: [], resources: []}
workflows:
  main: {type: Router, entry_agent: router, sub_agents: [router], summarizer: router, final_writer: writer}
""",
            )
            self._write(
                local,
                "override.yaml",
                """
version: 1.0.0
agents:
  router: {identity: mine, instruction: mine, model: fake, allowed_mcp_resources: [], resources: []}
""",
            )
            with mock.patch.dict(
                os.environ,
                {"WORKFLOW_LIBS_PATH": str(standard), "LOCAL_WORKFLOW_LIBS_PATH": str(local)},
                clear=False,
            ):
                config = load_workflow_libs()
        self.assertEqual(config.agents["router"].identity, "mine", "local dir must override the standard one")
        self.assertIn("main", config.workflows)

    def test_explicit_paths_beat_the_environment(self) -> None:
        with TemporaryDirectory() as explicit_dir, TemporaryDirectory() as env_dir:
            explicit, env = Path(explicit_dir), Path(env_dir)
            document = """
version: 1.0.0
agents:
  router: {identity: %s, instruction: x, model: fake, allowed_mcp_resources: [], resources: []}
  writer: {identity: w, instruction: w, model: fake, allowed_mcp_resources: [], resources: []}
workflows:
  main: {type: Router, entry_agent: router, sub_agents: [router], summarizer: router, final_writer: writer}
"""
            self._write(explicit, "a.yaml", document % "explicit")
            self._write(env, "a.yaml", document % "environment")
            with mock.patch.dict(os.environ, {"WORKFLOW_LIBS_PATH": str(env)}, clear=False):
                config = load_workflow_libs(standard_path=explicit)
        self.assertEqual(config.agents["router"].identity, "explicit")

    def test_duplicates_within_one_source_are_still_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            document = """
version: 1.0.0
agents:
  writer: {identity: w, instruction: w, model: fake, allowed_mcp_resources: [], resources: []}
"""
            self._write(root, "a.yaml", document)
            self._write(root, "b.yaml", document)
            with self.assertRaisesRegex(ConfigError, "duplicate_definition"):
                load_workflow_libs(standard_path=root)


class BundledConfigTests(unittest.TestCase):
    """The config the kit ships must load as one directory, not one file at a time."""

    def test_workflow_libs_directory_loads_as_a_whole(self) -> None:
        config = load_workflow_libs(standard_path=WORKFLOW_LIBS, known_mcp_resources=bundled_mcp_names())
        self.assertEqual(len(config.workflows), 4, f"expected the four shipped examples, got {sorted(config.workflows)}")

    def test_workflow_libs_load_together_with_every_shipped_mcp_card(self) -> None:
        """The real deployment loads both directories; the cards must satisfy the config."""
        config = load_workflow_libs(standard_path=WORKFLOW_LIBS, known_mcp_resources=bundled_mcp_names())
        declared = {name for agent in config.agents.values() for name in agent.allowed_mcp_resources}
        self.assertTrue(declared <= set(bundled_mcp_names()), f"unknown cards: {sorted(declared - set(bundled_mcp_names()))}")

    def test_every_shipped_example_declares_its_version(self) -> None:
        for path in sorted(WORKFLOW_LIBS.glob("*.yaml")):
            with self.subTest(path=path.name):
                self.assertIn("\nversion: 1.0.0", "\n" + path.read_text(encoding="utf-8"))

    def test_agent_definitions_directory_loads_all_four_agents(self) -> None:
        config = load_workflow_yaml(AGENT_DEFINITIONS, known_mcp_resources=bundled_mcp_names())
        self.assertEqual(
            set(config.agents),
            {"biology-collaborator", "data-collaborator", "materials-collaborator", "researcher-task-agent"},
        )

    def test_the_duplicate_workflow_directory_is_gone(self) -> None:
        legacy = KIT_ROOT / "agent-definitions" / "workflows"
        remaining = [path.name for path in legacy.glob("*.yaml")] if legacy.exists() else []
        self.assertEqual(remaining, [], "agent-definitions/workflows must only point at libs/workflow-libs")

    def test_every_shipped_agent_definition_declares_identity(self) -> None:
        for path in sorted(AGENT_DEFINITIONS.glob("*.yaml")):
            with self.subTest(path=path.name):
                agents = yaml.safe_load(path.read_text(encoding="utf-8")).get("agents", {})
                self.assertTrue(agents, f"{path.name} has no agents: wrapper")
                for name, body in agents.items():
                    self.assertIn("identity", body, f"{path.name}:{name} is missing identity")

    def test_every_workflow_helper_points_at_a_workflow_that_exists(self) -> None:
        """`workflow_helper.value.workflow` is not validated by the registry, so a
        typo survives loading and sends the researcher looking for a missing
        workflow (ai4-4zjz). Check the shipped ones here instead."""
        config = load_workflow_libs(standard_path=WORKFLOW_LIBS, known_mcp_resources=bundled_mcp_names())
        helpers = [
            path for path in (KIT_ROOT / "libs" / "agent-libs").rglob("*.yaml")
            if (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("kind") == "workflow_helper"
        ]
        self.assertTrue(helpers, "expected at least one shipped workflow_helper")
        for path in helpers:
            target = yaml.safe_load(path.read_text(encoding="utf-8"))["value"]["workflow"]
            with self.subTest(path=path.name):
                self.assertIn(target, config.workflows, f"{path.name} references unknown workflow {target!r}")


class EnvExampleTests(unittest.TestCase):
    """A variable the code requires must be discoverable in `.env.example`."""

    REQUIRED = (
        "SCIWEAVE_AGENT_ID",
        "SCIWEAVE_SUBSCRIBER_TOPICS",
        "AGENT_LIBS_PATH",
        "MCP_LIBS_PATH",
        "WORKFLOW_LIBS_PATH",
        "LOCAL_AGENT_LIBS",
        "LOCAL_MCP_LIBS",
        "LOCAL_WORKFLOW_LIBS_PATH",
    )

    def _declared(self) -> list[str]:
        text = (KIT_ROOT / ".env.example").read_text(encoding="utf-8")
        return [line.split("=", 1)[0].strip() for line in text.splitlines() if "=" in line and not line.strip().startswith("#")]

    def test_required_variables_are_documented(self) -> None:
        declared = self._declared()
        for name in self.REQUIRED:
            with self.subTest(name=name):
                self.assertIn(name, declared)

    def test_no_variable_is_declared_twice(self) -> None:
        declared = self._declared()
        duplicates = sorted({name for name in declared if declared.count(name) > 1})
        self.assertEqual(duplicates, [], "duplicate entries in .env.example")

    def test_the_example_file_alone_satisfies_the_subscriber_required_variables(self) -> None:
        """`cp .env.example .env` must be enough to start gateway/subscriber."""
        values = {}
        for line in (KIT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        for name in ("SCIWEAVE_AGENT_ID", "SCIWEAVE_SUBSCRIBER_TOPICS"):
            with self.subTest(name=name):
                self.assertTrue(values.get(name), f"{name} is still an empty placeholder in .env.example")


class VersionEnforcementTests(unittest.TestCase):
    def test_load_config_ignores_version_while_file_loading_enforces_it(self) -> None:
        raw = {
            "version": "2.0.0",
            "agents": {"router": {"identity": "r", "instruction": "r", "model": "fake", "allowed_mcp_resources": [], "resources": []},
                       "writer": {"identity": "w", "instruction": "w", "model": "fake", "allowed_mcp_resources": [], "resources": []}},
            "workflows": {"main": {"type": "Router", "entry_agent": "router", "sub_agents": ["router"], "summarizer": "router", "final_writer": "writer"}},
        }
        self.assertIn("main", load_config(raw).workflows)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "a.yaml"
            path.write_text(
                "version: 2.0.0\nagents: {}\nworkflows: {}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "unsupported_config_version"):
                load_workflow_yaml(path)


if __name__ == "__main__":
    unittest.main()
