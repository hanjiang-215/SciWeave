"""The domain cards are a capability surface, not a mirror of the services.

`libs/mcp-libs/` is the task-agent default configuration. The management MCPs
behind `research-mapping` and `research-wiki` also expose submit / review /
formalize tools, and nothing in the runtime filters tools by capability: a card
that lists them hands them to every agent that mounts the server. So the cards
list only the read/centre tools, and this file pins that boundary from both
directions — the whitelist, and the fact that the retained entries still match
the service definitions word for word.

The service modules are read with `ast` rather than imported: importing them
needs `audit_trail` on the path, which only the centre workspace provides, and
a card test should not depend on a second project being installed.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from work_agent_runtime import load_mcp_registry

KIT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = KIT_ROOT.parents[3]
MCP_LIBS = KIT_ROOT / "libs" / "mcp-libs"

SERVICES = {
    "research-mapping": REPO_ROOT
    / "sci-weave/centre-control/research-map/src/research_mapping/management.py",
    "research-wiki": REPO_ROOT
    / "sci-weave/centre-control/research-wiki/src/llm_wiki/management.py",
}

# The task-agent surface. Everything else those two services define is an
# Owner-side write and must stay off the card.
ALLOWED = {
    "research-mapping": {
        "get_formal_mapping",
        "get_formal_mapping_at_revision",
        "list_candidates",
    },
    "research-wiki": {
        "get_formal_wiki",
        "list_wiki_candidates",
    },
}

# Kept for the record: if one of these ever comes back, the reason has to be
# argued rather than merged silently.
PRE_REVIEW_EXCEPTIONS = {"list_reviewable_candidates", "list_reviewable_wiki_candidates"}

OWNER_SIDE = {
    "research-mapping": {
        "list_reviewable_candidates", "submit_candidate", "preview_candidate",
        "record_review", "formalize_candidate", "reconcile_formalization",
        "append_prereview_log", "create_merged_candidate",
    },
    "research-wiki": {
        "list_reviewable_wiki_candidates", "submit_wiki_candidate",
        "preview_wiki_review", "create_wiki_merge_request", "decide_wiki_review",
        "formalize_wiki", "reconcile_wiki_formalization", "append_prereview_log",
        "create_merged_candidate",
    },
}


def service_tools(domain: str) -> dict[str, dict]:
    """Read TOOL_DEFINITIONS out of a service module without importing it."""
    tree = ast.parse(SERVICES[domain].read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(target, "id", None) == "TOOL_DEFINITIONS" for target in node.targets
        ):
            definitions = ast.literal_eval(node.value)
            return {item["name"]: item for item in definitions}
    raise AssertionError(f"TOOL_DEFINITIONS not found in {SERVICES[domain]}")


def card_tools(domain: str) -> dict[str, dict]:
    registry = load_mcp_registry(standard_mcp_libs=str(MCP_LIBS))
    return registry.catalog()[domain]["tools"]


class ReadOnlyWhitelistTests(unittest.TestCase):
    def test_each_domain_card_lists_exactly_the_task_agent_tools(self):
        for domain, expected in ALLOWED.items():
            with self.subTest(domain=domain):
                self.assertEqual(set(card_tools(domain)), expected)

    def test_no_owner_side_tool_is_advertised(self):
        for domain, forbidden in OWNER_SIDE.items():
            with self.subTest(domain=domain):
                leaked = set(card_tools(domain)) & forbidden
                self.assertEqual(
                    leaked,
                    set(),
                    f"{domain} advertises Owner-side tools to a researcher's Work Agent",
                )

    def test_the_whitelist_and_the_exclusions_cover_every_service_tool(self):
        """A new service tool must be classified, not silently inherited or dropped."""
        for domain in ALLOWED:
            with self.subTest(domain=domain):
                classified = ALLOWED[domain] | OWNER_SIDE[domain]
                self.assertEqual(
                    classified,
                    set(service_tools(domain)),
                    f"{domain}: the service defines tools this list does not classify",
                )

    def test_every_dropped_tool_is_either_a_write_or_a_pinned_exception(self):
        """The line is capability, not taste — with exactly two documented exceptions.

        `list_reviewable_*` need only read/centre, yet they are dropped: they
        serve the candidate *pre-review* queue, which belongs to the centre, and
        keeping them only on one side is the asymmetry ai4-tj83 fixed. Every
        other dropped tool must genuinely need a non-read capability, so a
        future read tool cannot be dropped without saying why.
        """
        for domain, dropped in OWNER_SIDE.items():
            capabilities = self._capabilities(domain)
            for tool in dropped:
                with self.subTest(domain=domain, tool=tool):
                    self.assertIn(tool, capabilities, f"{tool} is not in _TOOL_CAPABILITIES")
                    if tool in PRE_REVIEW_EXCEPTIONS:
                        self.assertIn("centre", capabilities[tool], f"{tool} is not a centre tool")
                        continue
                    self.assertNotIn(
                        "read",
                        capabilities[tool],
                        f"{tool} needs only read; dropping it was not justified",
                    )

    def test_the_pre_review_exceptions_are_symmetric_across_domains(self):
        """One domain keeping what the other drops is what made this confusing."""
        mapping = {tool for tool in PRE_REVIEW_EXCEPTIONS if tool in ALLOWED["research-mapping"] | OWNER_SIDE["research-mapping"]}
        wiki = {tool for tool in PRE_REVIEW_EXCEPTIONS if tool in ALLOWED["research-wiki"] | OWNER_SIDE["research-wiki"]}
        self.assertEqual(len(mapping), 1)
        self.assertEqual(len(wiki), 1)
        for domain, tool in (("research-mapping", mapping.pop()), ("research-wiki", wiki.pop())):
            with self.subTest(domain=domain):
                self.assertNotIn(tool, ALLOWED[domain])

    def _capabilities(self, domain: str) -> dict[str, set[str]]:
        tree = ast.parse(SERVICES[domain].read_text(encoding="utf-8"))
        constants: dict[str, set[str]] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                name = getattr(node.targets[0], "id", None)
                value = node.value
                if name and isinstance(value, ast.Call) and getattr(value.func, "id", None) == "frozenset":
                    constants[name] = set(ast.literal_eval(value.args[0]))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                getattr(target, "id", None) == "_TOOL_CAPABILITIES" for target in node.targets
            ):
                # The values are names of the frozensets above, not literals.
                return {
                    key: constants[value.id]
                    for key, value in zip(
                        (ast.literal_eval(key) for key in node.value.keys),
                        node.value.values,
                    )
                }
        raise AssertionError(f"_TOOL_CAPABILITIES not found in {SERVICES[domain]}")


class RetainedToolFidelityTests(unittest.TestCase):
    def test_description_matches_the_service_word_for_word(self):
        for domain in ALLOWED:
            service = service_tools(domain)
            for name, tool in card_tools(domain).items():
                with self.subTest(domain=domain, tool=name):
                    self.assertEqual(tool["description"], service[name]["description"])

    def test_input_schema_matches_the_service_word_for_word(self):
        for domain in ALLOWED:
            service = service_tools(domain)
            for name, tool in card_tools(domain).items():
                with self.subTest(domain=domain, tool=name):
                    self.assertEqual(tool["input"], service[name]["inputSchema"])

    def test_additional_properties_is_closed_like_the_service(self):
        """The cards used to omit this; it is the one schema key that changes behaviour."""
        for domain in ALLOWED:
            for name, tool in card_tools(domain).items():
                with self.subTest(domain=domain, tool=name):
                    self.assertIs(tool["input"].get("additionalProperties"), False)

    def test_every_tool_declares_its_output_shape(self):
        for domain in ALLOWED:
            for name, tool in card_tools(domain).items():
                with self.subTest(domain=domain, tool=name):
                    self.assertTrue(tool["output"], f"{name} has no output shape")

    def test_the_formal_output_shape_names_the_approver(self):
        """ai4-2raq: published_by is how a caller learns who the project owner is."""
        registry = load_mcp_registry(standard_mcp_libs=str(MCP_LIBS))
        tools = registry.catalog()["research-mapping"]["tools"]
        for name in ("get_formal_mapping", "get_formal_mapping_at_revision"):
            with self.subTest(tool=name):
                self.assertIn("published_by", tools[name]["output"])


class UntouchedCardTests(unittest.TestCase):
    """draft-buffer and email-service are the task agent's own write targets."""

    def test_draft_buffer_keeps_all_seven_tools(self):
        self.assertEqual(
            set(card_tools("draft-buffer")),
            {
                "create_draft", "update_draft", "submit_draft", "list_drafts",
                "read_draft", "review_draft", "mark_promoted",
            },
        )

    def test_email_service_keeps_both_tools(self):
        self.assertEqual(set(card_tools("email-service")), {"send_notification", "get_notification_status"})

    def test_sciencepal_keeps_its_five_tools(self):
        self.assertEqual(
            set(card_tools("sciencepal")),
            {
                "sciencepal_start", "sciencepal_status", "sciencepal_collect",
                "sciencepal_cancel", "sciencepal_agents",
            }
            & set(card_tools("sciencepal")),
        )
        self.assertEqual(len(card_tools("sciencepal")), 5)


class PlaceholderCardTests(unittest.TestCase):
    def test_the_unbacked_local_literature_placeholder_is_gone(self):
        """It advertised a `search` tool with no service behind it."""
        self.assertFalse((KIT_ROOT / "libs" / "local-mcp-libs" / "local-literature.yaml").exists())

    def test_an_empty_local_directory_is_still_accepted(self):
        """Removing the only card must not break the documented local override."""
        registry = load_mcp_registry(
            standard_mcp_libs=str(MCP_LIBS),
            local_mcp_libs=str(KIT_ROOT / "libs" / "local-mcp-libs"),
        )
        self.assertIn("research-mapping", [resource.name for resource in registry.resources])


if __name__ == "__main__":
    unittest.main()
