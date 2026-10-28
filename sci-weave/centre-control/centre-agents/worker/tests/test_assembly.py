"""Assembly tests: environment in, one runnable configuration out (ai4-349h).

``load_centre_config`` is the highest seam in the worker: a root directory and an
environment mapping go in, a ``CentreConfig`` comes out. Every test below asserts
what that object says, except the ones under ``ShippedTreeTests`` — those check
the repository itself, because a config that only works against fixtures is how
"the file is in the repo but not in the image" happens.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from centre_fixtures import DEFINITION, ENVIRON, build_tree
from task_agent_worker.assembly import (
    DEFAULT_WORKFLOW,
    RULE_SET_PLACEHOLDER,
    CentreConfigError,
    centre_root,
    load_centre_config,
)


class _TreeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = build_tree(Path(self.tmp.name))

    def load(self, environ: dict | None = None, **overrides: str):
        return load_centre_config(
            {**(ENVIRON if environ is None else environ), **overrides}, root=self.root
        )

    def rewrite_definition(self, body: str) -> None:
        (self.root / "definitions" / "centre-prereview.yaml").write_text(body, encoding="utf-8")


class AssemblyLoadTests(_TreeCase):
    def test_one_workflow_is_selected_by_default(self) -> None:
        config = self.load()
        self.assertEqual(config.workflow_name, DEFAULT_WORKFLOW)
        self.assertEqual(config.sequence, ("step-read", "step-write"))
        self.assertEqual([agent.name for agent in config.agents], ["step-read", "step-write"])

    def test_each_agent_gets_only_its_own_servers(self) -> None:
        config = self.load()
        self.assertEqual(sorted(config.servers("step-read")), ["research-mapping", "research-wiki"])
        self.assertEqual(sorted(config.servers("step-write")), ["email-service", "research-mapping"])

    def test_each_agent_gets_only_its_own_tool_allowlist(self) -> None:
        config = self.load()
        self.assertEqual(
            config.tools("step-read"),
            {
                "research-mapping": ["list_reviewable_candidates"],
                "research-wiki": ["list_reviewable_wiki_candidates"],
            },
        )
        # `append_prereview_log` exists on the same server the reader uses; only
        # the filter keeps it out of the reader's hands.
        self.assertNotIn("append_prereview_log", config.tools("step-read")["research-mapping"])

    def test_the_one_config_file_declares_every_server_any_step_may_use(self) -> None:
        # fast-agent resolves `servers=` against `mcp.servers` in the file, so the
        # union must be there even though each decorator names only its own.
        document = yaml.safe_load(self.load().fast_agent_config())
        self.assertEqual(
            sorted(document["mcp"]["servers"]), ["email-service", "research-mapping", "research-wiki"]
        )
        self.assertEqual(document["mcp"]["servers"]["research-mapping"]["transport"], "http")
        self.assertEqual(
            document["mcp"]["servers"]["research-mapping"]["url"], ENVIRON["RESEARCH_MAPPING_MCP_URL"]
        )

    def test_the_two_plain_settings_are_always_present(self) -> None:
        document = yaml.safe_load(self.load().fast_agent_config())
        self.assertFalse(document["compaction"]["auto"])
        self.assertTrue(document["session_history"])

    def test_the_rule_set_version_is_substituted_into_instructions(self) -> None:
        config = self.load()
        self.assertEqual(config.rule_set_version, "1.0.0")
        self.assertIn("rule set 1.0.0", config.instruction("step-write"))
        self.assertNotIn(RULE_SET_PLACEHOLDER, config.instruction("step-write"))

    def test_the_resolved_paths_are_reported_for_diagnostics(self) -> None:
        config = self.load()
        self.assertEqual(
            sorted(config.paths),
            ["CENTRE_DEFINITIONS_PATH", "CENTRE_MCP_LIBS_PATH", "CENTRE_RULES_DIR"],
        )
        # The card directory as a path, not a string: callers that need to read a
        # card's raw document should not be re-parsing `paths`.
        self.assertEqual(config.cards_root, self.root / "libs" / "mcp-libs")


class AssemblyRejectionTests(_TreeCase):
    def test_a_missing_definitions_directory_is_refused(self) -> None:
        with self.assertRaises(CentreConfigError) as caught:
            self.load(CENTRE_DEFINITIONS_PATH=str(self.root / "nowhere"))
        self.assertEqual(caught.exception.variable, "CENTRE_DEFINITIONS_PATH")
        self.assertIn("does not exist", caught.exception.detail)

    def test_an_undeclared_mcp_resource_names_the_agent_and_the_resource(self) -> None:
        self.rewrite_definition(
            DEFINITION.replace(
                "allowed_mcp_resources: [research-mapping, research-wiki]", "allowed_mcp_resources: [ghost]"
            )
        )
        with self.assertRaises(CentreConfigError) as caught:
            self.load()
        self.assertIn("step-read", caught.exception.detail)
        self.assertIn("ghost", caught.exception.detail)

    def test_an_undeclared_tool_names_the_server_and_the_tool(self) -> None:
        self.rewrite_definition(
            DEFINITION.replace(
                "research-mapping: [list_reviewable_candidates]", "research-mapping: [formalize_candidate]"
            )
        )
        with self.assertRaises(CentreConfigError) as caught:
            self.load()
        self.assertIn("research-mapping.formalize_candidate", caught.exception.detail)

    def test_a_tool_filter_on_an_undeclared_resource_is_refused(self) -> None:
        # Declaring a filter without declaring the resource would look like a
        # working tool grant while `servers=` never mentions the server.
        self.rewrite_definition(
            DEFINITION.replace(
                "      research-mapping: [append_prereview_log]",
                "      research-mapping: [append_prereview_log]\n      research-wiki: [get_formal_wiki]",
            )
        )
        with self.assertRaises(CentreConfigError) as caught:
            self.load()
        self.assertIn("research-wiki", caught.exception.detail)
        self.assertIn("step-write", caught.exception.detail)

    def test_a_workflow_name_nobody_declares_is_refused_rather_than_defaulted(self) -> None:
        with self.assertRaises(CentreConfigError) as caught:
            self.load(SCIWEAVE_WORKFLOW="ghost")
        self.assertEqual(caught.exception.variable, "SCIWEAVE_WORKFLOW")
        self.assertIn("centre-prereview", caught.exception.detail)

    def test_a_missing_url_variable_fails_at_load_not_at_run(self) -> None:
        with self.assertRaises(CentreConfigError) as caught:
            load_centre_config({"RESEARCH_MAPPING_MCP_URL": "https://m.invalid/mcp"}, root=self.root)
        self.assertEqual(caught.exception.variable, "CENTRE_MCP_LIBS_PATH")
        self.assertIn("LLM_WIKI_MCP_URL", caught.exception.detail)

    def test_an_ambiguous_rule_set_directory_is_refused(self) -> None:
        (self.root / "rules" / "1.1.0.json").write_text(
            json.dumps({"version": "1.1.0", "checks": ["x"]}), encoding="utf-8"
        )
        with self.assertRaises(CentreConfigError) as caught:
            self.load()
        self.assertEqual(caught.exception.variable, "CENTRE_PREREVIEW_RULE_SET_VERSION")

    def test_an_explicit_rule_set_version_resolves_among_several(self) -> None:
        (self.root / "rules" / "1.1.0.json").write_text(
            json.dumps({"version": "1.1.0", "checks": ["x"]}), encoding="utf-8"
        )
        config = self.load(CENTRE_PREREVIEW_RULE_SET_VERSION="1.1.0")
        self.assertEqual(config.rule_set_version, "1.1.0")

    def test_a_rule_set_whose_version_disagrees_with_its_filename_is_refused(self) -> None:
        (self.root / "rules" / "1.0.0.json").write_text(
            json.dumps({"version": "9.9.9", "checks": ["x"]}), encoding="utf-8"
        )
        with self.assertRaises(CentreConfigError) as caught:
            self.load()
        self.assertEqual(caught.exception.variable, "CENTRE_RULES_DIR")

    def test_an_empty_checks_list_is_refused(self) -> None:
        (self.root / "rules" / "1.0.0.json").write_text(
            json.dumps({"version": "1.0.0", "checks": []}), encoding="utf-8"
        )
        with self.assertRaises(CentreConfigError) as caught:
            self.load()
        self.assertIn("non-empty checks", caught.exception.detail)

    def test_a_rule_set_version_that_does_not_exist_is_refused(self) -> None:
        with self.assertRaises(CentreConfigError) as caught:
            self.load(CENTRE_PREREVIEW_RULE_SET_VERSION="2.0.0")
        self.assertIn("2.0.0", caught.exception.detail)

    def test_a_broken_card_is_reported_against_the_libs_variable(self) -> None:
        (self.root / "libs" / "mcp-libs" / "research-mapping" / "mcp.json").write_text("{", encoding="utf-8")
        with self.assertRaises(CentreConfigError) as caught:
            self.load()
        self.assertEqual(caught.exception.variable, "CENTRE_MCP_LIBS_PATH")
        self.assertIn("card_invalid", caught.exception.detail)


class ShippedTreeTests(unittest.TestCase):
    """The repository's own ``definitions/``, ``libs/`` and ``rules/``."""

    def setUp(self) -> None:
        self.base = centre_root()
        self.config = load_centre_config(dict(ENVIRON), root=self.base)

    def test_the_shipped_configuration_loads(self) -> None:
        self.assertEqual(self.config.workflow_name, "centre-prereview")
        self.assertEqual(
            self.config.sequence,
            (
                "centre-prereview-intake",
                "centre-prereview-audit",
                "centre-prereview-conflict",
                "centre-prereview-verdict",
                "centre-prereview-writer",
            ),
        )

    def test_only_the_writer_can_append_a_prereview_log(self) -> None:
        writers = [
            agent.name
            for agent in self.config.agents
            if "append_prereview_log" in self.config.tools(agent.name).get("research-mapping", [])
        ]
        self.assertEqual(writers, ["centre-prereview-writer"])

    def test_the_fact_checking_steps_have_no_mcp_access_at_all(self) -> None:
        # If one of them could read the domain MCP it could also fetch a second
        # snapshot, and the same-instant premise behind the conflict matrix would
        # be gone without anything saying so.
        for name in ("centre-prereview-audit", "centre-prereview-conflict", "centre-prereview-verdict"):
            with self.subTest(agent=name):
                self.assertEqual(self.config.servers(name), {})

    def test_no_shipped_card_exposes_an_adjudication_tool(self) -> None:
        # The capability ceiling is not enforced by the definition layer: the
        # model sees full tool descriptions regardless of how narrow the YAML is.
        forbidden = {"formalize_candidate", "formalize_wiki", "decide_wiki_review", "record_review"}
        for name, card in self.config.cards.items():
            with self.subTest(card=name):
                self.assertEqual(forbidden & set(card.tools), set())

    def test_the_shipped_rules_file_satisfies_the_domain_contract(self) -> None:
        # Assert against the domain side's own resolver, not a copy of its rules:
        # two validators drift, and the drift shows up as `rule_set_missing` in
        # production while the test still passes. `research_mapping` is a sibling
        # project, so its source tree goes on the path here rather than becoming a
        # dependency of the worker.
        mapping_src = self.base.parent / "research-map" / "src"
        if not mapping_src.is_dir():  # pragma: no cover - the checkout always has it
            self.skipTest(f"{mapping_src} is not present")
        original = list(sys.path)
        sys.path.insert(0, str(mapping_src))
        try:
            from research_mapping.prereview import resolve_rule_set

            document = resolve_rule_set(str(self.base / "rules"), "1.0.0")
        finally:
            sys.path[:] = original
        self.assertEqual(document["version"], "1.0.0")
        self.assertIn("冲突", document["checks"])

    def test_every_shipped_agent_states_a_model(self) -> None:
        for agent in self.config.agents:
            with self.subTest(agent=agent.name):
                self.assertTrue(agent.model.strip())


if __name__ == "__main__":
    unittest.main()
