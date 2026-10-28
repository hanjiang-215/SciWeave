"""The shipped literature card must survive the runtime's own loader.

`custom-mcp/literature-search/tests/test_card.py` checks the card against the
service. This checks it against the runtime, which is where a stdio startup is
rejected wholesale if it deviates from one exact argv shape. Both are needed:
the card can agree with its server and still be unloadable.
"""

import json
import unittest
from pathlib import Path

from work_agent_runtime import load_mcp_registry

KIT_ROOT = Path(__file__).resolve().parents[2]
MCP_LIBS = KIT_ROOT / "libs" / "mcp-libs"
CARD = MCP_LIBS / "literature-search" / "mcp.json"


class LiteratureCardTests(unittest.TestCase):
    def test_the_card_ships_with_the_kit(self):
        self.assertTrue(CARD.is_file(), f"{CARD} is missing")

    def test_the_registry_loads_it_alongside_the_domain_cards(self):
        """A malformed startup raises unsafe_startup for the whole directory."""
        registry = load_mcp_registry(standard_mcp_libs=str(MCP_LIBS))
        names = [resource.name for resource in registry.resources]
        self.assertIn("literature-search", names)
        self.assertIn("draft-buffer", names, "adding one card must not drop the others")

    def test_it_is_stdio_with_the_whitelisted_startup(self):
        registry = load_mcp_registry(standard_mcp_libs=str(MCP_LIBS))
        card = registry.get("literature-search")
        self.assertEqual(card.transport, "stdio")
        self.assertEqual(dict(card.startup)["executable"], "uv")
        self.assertEqual(dict(card.startup)["args"], ["run", "--env-file", ".env", "python", "src/main.py"])
        self.assertEqual(dict(card.startup)["project_dir_env"], "LITERATURE_MCP_PROJECT_DIR")

    def test_it_exposes_only_the_two_read_tools(self):
        registry = load_mcp_registry(standard_mcp_libs=str(MCP_LIBS))
        card = registry.get("literature-search")
        self.assertEqual(set(card.tools), {"search", "get_abstract"})

    def test_every_tool_carries_a_description_and_a_typed_input(self):
        registry = load_mcp_registry(standard_mcp_libs=str(MCP_LIBS))
        card = registry.get("literature-search")
        for name, tool in card.tools.items():
            with self.subTest(tool=name):
                self.assertTrue(tool.description, name)
                self.assertEqual(tool.input_schema.get("type"), "object", name)
                self.assertTrue(tool.input_schema.get("properties"), name)

    def test_neither_tool_claims_a_write(self):
        """`allowed` is free text in every card here; the claim still has to be read-only."""
        registry = load_mcp_registry(standard_mcp_libs=str(MCP_LIBS))
        card = registry.get("literature-search")
        for name, tool in card.tools.items():
            with self.subTest(tool=name):
                self.assertTrue(tool.allowed, f"{name} must say what it is allowed to do")
                claim = " ".join(tool.allowed).lower()
                self.assertIn("read", claim)
                for verb in ("write", "submit", "formalize", "delete"):
                    self.assertNotIn(verb, claim, f"{name} must not claim to {verb}")

    def test_the_card_declares_the_environment_it_reads(self):
        """index.json/docs promise these names; a rename here silently defaults."""
        data = json.loads(CARD.read_text(encoding="utf-8"))
        self.assertEqual(
            set(data["environment"]),
            {
                "LITERATURE_ARXIV_ENDPOINT",
                "LITERATURE_CROSSREF_ENDPOINT",
                "LITERATURE_CONTACT_EMAIL",
                "LITERATURE_TIMEOUT_SECONDS",
            },
        )

    def test_the_service_project_exists_where_the_card_points(self):
        data = json.loads(CARD.read_text(encoding="utf-8"))
        project = KIT_ROOT / "custom-mcp" / "literature-search"
        self.assertTrue((project / "pyproject.toml").is_file())
        self.assertTrue((project / "src" / "main.py").is_file())
        self.assertTrue((project / data["startup"]["args"][-1]).is_file())


if __name__ == "__main__":
    unittest.main()
