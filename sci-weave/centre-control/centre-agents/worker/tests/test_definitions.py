"""Definition-layer tests: one directory in, one namespace out (ai4-349h).

Every test here goes through ``load_definitions``, the highest seam in the
module: a temporary directory and a document go in, a ``CentreDefinitions``
comes out. Nothing asserts how the YAML is walked internally.
"""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from task_agent_worker.definitions import DefinitionError, load_definitions

MINIMAL = textwrap.dedent(
    """\
    version: 1.0.0
    agents:
      alpha:
        identity: first
        instruction: do the first thing
        model: configure-in-your-own-environment
        allowed_mcp_resources: []
        resources: []
    """
)


def _workflow(body: str, name: str = "flow", **fields: object) -> str:
    """``MINIMAL`` plus one workflow block, dedented by the caller."""
    lines = [body.rstrip("\n"), "workflows:", f"  {name}:"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"    {key}: [{', '.join(str(item) for item in value)}]")
        elif isinstance(value, bool):
            lines.append(f"    {key}: {'true' if value else 'false'}")
        else:
            lines.append(f"    {key}: {value}")
    return "\n".join(lines) + "\n"


class _DefinitionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name: str, body: str) -> Path:
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        return path

    def load(self, body: str):
        self.write("flow.yaml", body)
        return load_definitions(self.root)


class DefinitionLoadTests(_DefinitionTestCase):
    def test_loads_agents_and_a_chain_with_derived_fields(self) -> None:
        self.write(
            "flow.yaml",
            textwrap.dedent(
                """\
                version: 1.0.0
                agents:
                  alpha:
                    identity: first
                    instruction: do the first thing
                    model: configure-in-your-own-environment
                    allowed_mcp_resources: []
                    resources: []
                  omega:
                    identity: last
                    instruction: do the last thing
                    model: configure-in-your-own-environment
                    allowed_mcp_resources: []
                    resources: []
                workflows:
                  one-chain:
                    type: Chain
                    sequence: [alpha, omega]
                """
            ),
        )
        definitions = load_definitions(self.root)
        self.assertEqual(sorted(definitions.agents), ["alpha", "omega"])
        workflow = definitions.workflow("one-chain")
        # The Task Agent template requires all three; a Chain derives them from
        # the order rather than making the author repeat what it already says.
        self.assertEqual(workflow.entry_agent, "alpha")
        self.assertEqual(workflow.summarizer, "omega")
        self.assertEqual(workflow.final_writer, "omega")
        self.assertTrue(workflow.cumulative)
        self.assertEqual([agent.name for agent in definitions.chain("one-chain")], ["alpha", "omega"])

    def test_cumulative_defaults_to_true_and_can_be_turned_off(self) -> None:
        self.write("flow.yaml", MINIMAL)
        self.assertEqual(len(load_definitions(self.root).agents), 1)
        self.assertFalse(
            self.load(_workflow(MINIMAL, type="Chain", sequence=["alpha"], cumulative=False))
            .workflow("flow")
            .cumulative
        )

    def test_a_missing_directory_is_an_error_not_an_empty_namespace(self) -> None:
        with self.assertRaises(DefinitionError) as caught:
            load_definitions(self.root / "nowhere")
        self.assertEqual(caught.exception.code, "no_definitions")

    def test_a_directory_of_documentation_only_is_an_error(self) -> None:
        self.write("schema.yaml", "version: 1.0.0\n")
        with self.assertRaises(DefinitionError) as caught:
            load_definitions(self.root)
        self.assertEqual(caught.exception.code, "no_definitions")

    def test_schema_yaml_is_skipped_rather_than_loaded(self) -> None:
        # The shipped directory holds schema.yaml next to the real definition. If
        # the loader tried to read it, every install would fail on a file that
        # documents the format instead of using it.
        self.write("schema.yaml", "version: 1.0.0\n# documentation only\n")
        self.write("flow.yaml", MINIMAL)
        self.assertEqual(sorted(load_definitions(self.root).agents), ["alpha"])

    def test_flat_single_agent_document_is_refused(self) -> None:
        self.write(
            "flat.yaml",
            textwrap.dedent(
                """\
                version: 1.0.0
                alpha:
                  identity: first
                  instruction: do the first thing
                  model: configure-in-your-own-environment
                """
            ),
        )
        with self.assertRaises(DefinitionError) as caught:
            load_definitions(self.root)
        self.assertEqual(caught.exception.code, "missing_field")


class DefinitionValidationTests(_DefinitionTestCase):
    def test_a_non_1x_version_is_refused(self) -> None:
        with self.assertRaises(DefinitionError) as caught:
            self.load(MINIMAL.replace("version: 1.0.0", "version: 2.0.0"))
        self.assertEqual(caught.exception.code, "unsupported_config_version")

    def test_an_unknown_top_level_key_is_named(self) -> None:
        with self.assertRaises(DefinitionError) as caught:
            self.load(MINIMAL + "typo_section: {}\n")
        self.assertEqual(caught.exception.code, "unknown_field")
        self.assertIn("typo_section", caught.exception.detail)

    def test_an_unknown_agent_key_is_named(self) -> None:
        body = MINIMAL.replace("    resources: []", "    resources: []\n    servers: [x]")
        with self.assertRaises(DefinitionError) as caught:
            self.load(body)
        self.assertEqual(caught.exception.code, "unknown_field")
        self.assertIn("servers", caught.exception.detail)

    def test_a_template_style_tools_key_is_refused(self) -> None:
        # `tools` means "sub-agents of an Agents-as-Tools workflow" in the Task
        # Agent template. Accepting it here would silently give it the other
        # meaning instead of telling the author the key is not this side's.
        body = MINIMAL.replace("    resources: []", "    resources: []\n    tools: [beta]")
        with self.assertRaises(DefinitionError) as caught:
            self.load(body)
        self.assertEqual(caught.exception.code, "unknown_field")

    def test_an_empty_instruction_is_refused(self) -> None:
        with self.assertRaises(DefinitionError) as caught:
            self.load(MINIMAL.replace("instruction: do the first thing", 'instruction: "  "'))
        self.assertEqual(caught.exception.code, "invalid_instruction")

    def test_an_empty_tool_allowlist_is_refused(self) -> None:
        body = MINIMAL.replace(
            "    allowed_mcp_resources: []",
            "    allowed_mcp_resources: [research-mapping]\n    allowed_tools:\n      research-mapping: []",
        )
        with self.assertRaises(DefinitionError) as caught:
            self.load(body)
        self.assertEqual(caught.exception.code, "invalid_tools")

    def test_an_unknown_workflow_type_is_refused(self) -> None:
        with self.assertRaises(DefinitionError) as caught:
            self.load(_workflow(MINIMAL, type="Router", sequence=["alpha"]))
        self.assertEqual(caught.exception.code, "unknown_workflow_type")

    def test_an_empty_sequence_is_refused(self) -> None:
        with self.assertRaises(DefinitionError) as caught:
            self.load(_workflow(MINIMAL, type="Chain", sequence=[]))
        self.assertEqual(caught.exception.code, "missing_sequence")

    def test_a_sequence_naming_an_undeclared_agent_is_refused(self) -> None:
        with self.assertRaises(DefinitionError) as caught:
            self.load(_workflow(MINIMAL, type="Chain", sequence=["alpha", "ghost"]))
        self.assertEqual(caught.exception.code, "unknown_agent")
        self.assertIn("ghost", caught.exception.detail)
        self.assertIn("alpha", caught.exception.detail)

    def test_the_same_agent_twice_in_one_chain_is_refused(self) -> None:
        with self.assertRaises(DefinitionError) as caught:
            self.load(_workflow(MINIMAL, type="Chain", sequence=["alpha", "alpha"]))
        self.assertEqual(caught.exception.code, "duplicate_sequence_entry")

    def test_a_duplicate_agent_name_across_files_is_refused(self) -> None:
        self.write("one.yaml", MINIMAL)
        self.write("two.yaml", MINIMAL)
        with self.assertRaises(DefinitionError) as caught:
            load_definitions(self.root)
        self.assertEqual(caught.exception.code, "duplicate_definition")
        self.assertIn("alpha", caught.exception.detail)

    def test_an_unknown_workflow_name_lists_the_known_ones(self) -> None:
        definitions = self.load(MINIMAL)
        with self.assertRaises(DefinitionError) as caught:
            definitions.workflow("nope")
        self.assertEqual(caught.exception.code, "unknown_workflow")
        self.assertIn("(none)", caught.exception.detail)


if __name__ == "__main__":
    unittest.main()
